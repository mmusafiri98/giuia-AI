import streamlit as st
from gradio_client import Client, handle_file
import tempfile
import shutil
import os
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
import traceback

print("🚀 Démarrage de l'application VimeoAI...")

# ===================================================================
# CONFIGURATION
# ===================================================================
st.set_page_config(page_title="VimeoAI - Video Generator", page_icon="🎬", layout="centered")

STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)
GENERATED_DIR = "generated_videos"
os.makedirs(GENERATED_DIR, exist_ok=True)

# CONFIGURATION DATABASE NEON
DATABASE_URL = "postgresql://neondb_owner:npg_b3qwDlLzV9YO@ep-icy-tooth-adi815w9-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"

# CLIENTS VIDEO
PRIMARY_CLIENT = "Lightricks/ltx-video-distilled"
FALLBACK_CLIENT = "multimodalart/wan-2-2-first-last-frame"

# ===================================================================
# DATABASE FUNCTIONS
# ===================================================================
def get_db_connection():
    """Connexion au database PostgreSQL Neon"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"❌ Errore connessione DB: {e}")
        return None

def init_database():
    """Initialise les tables du database"""
    conn = get_db_connection()
    if not conn:
        print("❌ Impossibile connettersi al database!")
        return False

    try:
        cur = conn.cursor()
        
        # Table USERS
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Table VIDEO_GENERATE
        cur.execute("""
            CREATE TABLE IF NOT EXISTS video_generate (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                prompt TEXT NOT NULL,                
                image_url TEXT,
                video_url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Table USER_RESET_PASSWORD
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_reset_password (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                reset_token VARCHAR(255) NOT NULL,
                expires_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP + INTERVAL '1 hour'),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                used BOOLEAN DEFAULT FALSE
            )
        """)

        conn.commit()
        cur.close()
        conn.close()
        print("✅ Database inizializzato con successo!")
        return True
    except Exception as e:
        print(f"❌ Errore inizializzazione DB: {e}")
        print(traceback.format_exc())
        try:
            conn.rollback()
        except:
            pass
        if conn:
            conn.close()
        return False

# Initialise le database au démarrage
init_database()

# ===================================================================
# UTILITY FUNCTIONS
# ===================================================================
def hash_password(password: str) -> str:
    """Hash password avec SHA256"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

# ===================================================================
# AUTHENTICATION FUNCTIONS
# ===================================================================
def register_user(username, email, password):
    """Enregistrer un nouvel utilisateur"""
    print(f"🔵 Tentativo registrazione: {username}, {email}")
    
    if not username or not email or not password:
        return False, "❌ Tous les champs sont obligatoires!"
    if len(password) < 6:
        return False, "❌ Le mot de passe doit contenir au moins 6 caractères!"

    conn = get_db_connection()
    if not conn:
        return False, "❌ Erreur de connexion à la base de données!"
    
    try:
        cur = conn.cursor()
        password_hash = hash_password(password)
        cur.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s) RETURNING id",
            (username, email, password_hash)
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ Utente registrato con ID: {user_id}")
        return True, f"✅ Inscription réussie!\n\nUsername: **{username}**\n\nVous pouvez maintenant vous connecter."
    except psycopg2.IntegrityError:
        print(f"❌ Username ou email déjà existant")
        try:
            conn.rollback()
        except:
            pass
        if conn:
            conn.close()
        return False, "❌ Ce nom d'utilisateur ou email existe déjà!"
    except Exception as e:
        print(f"❌ Errore registrazione: {e}")
        if conn:
            conn.close()
        return False, f"❌ Erreur: {str(e)}"

def login_user(username, password):
    """Connexion utilisateur"""
    print(f"🔵 Tentativo login: {username}")
    
    if not username or not password:
        return None, "❌ Entrez votre nom d'utilisateur et mot de passe!"
    
    conn = get_db_connection()
    if not conn:
        return None, "❌ Erreur de connexion à la base de données!"
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        password_hash = hash_password(password)
        cur.execute("SELECT id, username, email FROM users WHERE username = %s AND password_hash = %s", 
                   (username, password_hash))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if user:
            user_dict = {'id': user['id'], 'username': user['username'], 'email': user['email']}
            print(f"✅ Login riuscito per: {username}")
            return user_dict, "✅ Connexion réussie!"
        else:
            return None, "❌ Nom d'utilisateur ou mot de passe incorrect!"
    except Exception as e:
        print(f"❌ Errore login: {e}")
        if conn:
            conn.close()
        return None, f"❌ Erreur: {str(e)}"

def request_password_reset(email):
    """Demander un token de réinitialisation"""
    conn = get_db_connection()
    if not conn:
        return False, "❌ Erreur de connexion à la base de données!"
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        
        if not user:
            cur.close()
            conn.close()
            return False, "❌ Email non trouvé!"

        reset_token = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(hours=1)
        
        cur.execute(
            "INSERT INTO user_reset_password (user_id, reset_token, expires_at) VALUES (%s, %s, %s)",
            (user['id'], reset_token, expires_at)
        )
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"✅ Reset token generato per user_id {user['id']}")
        return True, f"✅ Token de réinitialisation généré!\n\n**Token:** `{reset_token}`\n\n⚠️ Copiez ce token pour réinitialiser votre mot de passe!"
    except Exception as e:
        print(f"❌ Errore reset request: {e}")
        if conn:
            conn.close()
        return False, f"❌ Erreur: {str(e)}"

def reset_password(reset_token, new_password):
    """Réinitialiser le mot de passe"""
    if len(new_password) < 6:
        return False, "❌ Le mot de passe doit contenir au moins 6 caractères!"
    
    conn = get_db_connection()
    if not conn:
        return False, "❌ Erreur de connexion à la base de données!"
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT id, user_id, expires_at, used FROM user_reset_password WHERE reset_token = %s",
            (reset_token,)
        )
        rec = cur.fetchone()
        
        if not rec:
            cur.close()
            conn.close()
            return False, "❌ Token invalide!"
        
        if rec['used']:
            cur.close()
            conn.close()
            return False, "❌ Token déjà utilisé!"
        
        if datetime.now() > rec['expires_at']:
            cur.close()
            conn.close()
            return False, "❌ Token expiré!"
        
        # Mettre à jour le mot de passe
        password_hash = hash_password(new_password)
        cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", 
                   (password_hash, rec['user_id']))
        cur.execute("UPDATE user_reset_password SET used = TRUE WHERE id = %s", 
                   (rec['id'],))
        conn.commit()
        cur.close()
        conn.close()
        
        return True, "✅ Mot de passe réinitialisé avec succès! Vous pouvez maintenant vous connecter."
    except Exception as e:
        print(f"❌ Errore reset password: {e}")
        if conn:
            conn.close()
        return False, f"❌ Erreur: {str(e)}"

# ===================================================================
# VIDEO FUNCTIONS
# ===================================================================
def save_video_to_db(user_id, prompt, video_path):
    """Sauvegarder le vidéo dans la base de données"""
    try:
        conn = get_db_connection()
        if not conn:
            return False
        
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO video_generate (user_id, prompt, video_url) VALUES (%s, %s, %s)",
            (user_id, prompt, video_path)
        )
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ Video salvato per user_id: {user_id}")
        return True
    except Exception as e:
        print(f"❌ Errore salvataggio video: {e}")
        if conn:
            conn.close()
        return False

def get_user_videos(user_id, limit=50):
    """Récupérer la galerie de vidéos de l'utilisateur"""
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT id, prompt, video_url, created_at FROM video_generate WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
            (user_id, limit)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"❌ Errore recupero video: {e}")
        if conn:
            conn.close()
        return []

def generate_video_with_fallback(prompt, image_path, width, height, duration):
    """Générer vidéo avec fallback automatique"""
    models_to_try = [
        (PRIMARY_CLIENT, "LTX Video", "primary"),
        (FALLBACK_CLIENT, "Wan 2.2 First-Last Frame", "wan2.2_first_last")
    ]
    
    last_error = None
    
    for model_space, model_name, model_type in models_to_try:
        try:
            st.info(f"🔄 Tentative avec **{model_name}**...")
            client = Client(model_space)
            
            if model_type == "primary":
                video_result, _ = client.predict(
                    prompt=prompt,
                    input_image_filepath=handle_file(image_path),
                    height_ui=height,
                    width_ui=width,
                    mode="image-to-video",
                    duration_ui=duration,
                    ui_frames_to_use=9,
                    seed_ui=42,
                    randomize_seed=True,
                    ui_guidance_scale=1,
                    improve_texture_flag=True,
                    api_name="/image_to_video"
                )
            elif model_type == "wan2.2_first_last":
                video_result = client.predict(
                    start_image_pil=handle_file(image_path),
                    end_image_pil=handle_file(image_path),
                    prompt=prompt,
                    negative_prompt="色调艳丽，过曝，静态，细节模糊不清",
                    duration_seconds=duration,
                    steps=8,
                    guidance_scale=1,
                    guidance_scale_2=1,
                    seed=42,
                    randomize_seed=True,
                    api_name="/generate_video_1"
                )
            
            st.session_state["current_model"] = model_space
            st.success(f"✅ Vidéo générée avec succès en utilisant **{model_name}**!")
            
            # Extraire le chemin du vidéo
            if isinstance(video_result, dict) and "video" in video_result:
                return video_result["video"]
            elif isinstance(video_result, str):
                return video_result
            elif isinstance(video_result, tuple) and len(video_result) > 0:
                return video_result[0] if isinstance(video_result[0], str) else video_result[0]["video"]
            else:
                raise ValueError(f"Format de résultat non reconnu: {type(video_result)}")
                
        except Exception as e:
            last_error = e
            st.warning(f"⚠️ **{model_name}** non disponible: {str(e)}")
            continue
    
    raise Exception(f"❌ Tous les modèles ont échoué. Dernière erreur: {str(last_error)}")

# ===================================================================
# SESSION STATE INITIALIZATION
# ===================================================================
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "user" not in st.session_state:
    st.session_state["user"] = None
if "current_model" not in st.session_state:
    st.session_state["current_model"] = PRIMARY_CLIENT
if "page" not in st.session_state:
    st.session_state["page"] = "login"

# ===================================================================
# LOGOUT FUNCTION
# ===================================================================
def logout():
    st.session_state["logged_in"] = False
    st.session_state["user"] = None
    st.session_state["page"] = "login"
    st.rerun()

# ===================================================================
# PAGE: LOGIN
# ===================================================================
if st.session_state["page"] == "login" and not st.session_state["logged_in"]:
    st.markdown("<h1 style='text-align: center; color: #4B0082;'>🔐 VimeoAI - Connexion</h1>", unsafe_allow_html=True)
    
    username = st.text_input("Nom d'utilisateur")
    password = st.text_input("Mot de passe", type="password")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Se connecter", use_container_width=True):
            user, message = login_user(username, password)
            if user:
                st.session_state["logged_in"] = True
                st.session_state["user"] = user
                st.session_state["page"] = "app"
                st.success(message)
                st.rerun()
            else:
                st.error(message)
    
    with col2:
        if st.button("Créer un compte", use_container_width=True):
            st.session_state["page"] = "register"
            st.rerun()
    
    if st.button("Mot de passe oublié?"):
        st.session_state["page"] = "forgot_password"
        st.rerun()
    
    st.stop()

# ===================================================================
# PAGE: REGISTER
# ===================================================================
if st.session_state["page"] == "register":
    st.markdown("<h1 style='text-align: center; color: #4B0082;'>📝 Créer un compte</h1>", unsafe_allow_html=True)
    
    new_username = st.text_input("Nom d'utilisateur")
    new_email = st.text_input("Email")
    new_password = st.text_input("Mot de passe", type="password")
    confirm_password = st.text_input("Confirmer le mot de passe", type="password")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("S'inscrire", use_container_width=True):
            if new_password != confirm_password:
                st.error("❌ Les mots de passe ne correspondent pas!")
            else:
                success, message = register_user(new_username, new_email, new_password)
                if success:
                    st.success(message)
                    st.info("Redirection vers la page de connexion...")
                    st.session_state["page"] = "login"
                    st.rerun()
                else:
                    st.error(message)
    
    with col2:
        if st.button("Retour", use_container_width=True):
            st.session_state["page"] = "login"
            st.rerun()
    
    st.stop()

# ===================================================================
# PAGE: FORGOT PASSWORD
# ===================================================================
if st.session_state["page"] == "forgot_password":
    st.markdown("<h1 style='text-align: center; color: #4B0082;'>🔑 Réinitialiser le mot de passe</h1>", unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["Demander un token", "Réinitialiser avec token"])
    
    with tab1:
        email = st.text_input("Votre email")
        if st.button("Envoyer le token"):
            success, message = request_password_reset(email)
            if success:
                st.success(message)
            else:
                st.error(message)
    
    with tab2:
        reset_token = st.text_input("Token de réinitialisation")
        new_pass = st.text_input("Nouveau mot de passe", type="password")
        confirm_pass = st.text_input("Confirmer le mot de passe", type="password")
        
        if st.button("Réinitialiser"):
            if new_pass != confirm_pass:
                st.error("❌ Les mots de passe ne correspondent pas!")
            else:
                success, message = reset_password(reset_token, new_pass)
                if success:
                    st.success(message)
                    st.session_state["page"] = "login"
                    st.rerun()
                else:
                    st.error(message)
    
    if st.button("Retour à la connexion"):
        st.session_state["page"] = "login"
        st.rerun()
    
    st.stop()

# ===================================================================
# PAGE: APPLICATION PRINCIPALE
# ===================================================================
if st.session_state["logged_in"] and st.session_state["user"]:
    # Header
    st.markdown("<h1 style='text-align: center; color: #4B0082;'>🎬 VimeoAI</h1>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align: center; color: #666;'>Bienvenue **{st.session_state['user']['username']}**!</p>", unsafe_allow_html=True)
    
    # Afficher le modèle actif
    model_names = {
        PRIMARY_CLIENT: "LTX Video",
        FALLBACK_CLIENT: "Wan 2.2 First-Last Frame"
    }
    current_model_name = model_names.get(st.session_state["current_model"], "Inconnu")
    st.info(f"🤖 Modèle actif: **{current_model_name}**")
    
    # Sidebar
    st.sidebar.header(f"👤 {st.session_state['user']['username']}")
    if st.sidebar.button("🔒 Déconnexion"):
        logout()
    
    st.sidebar.markdown("---")
    st.sidebar.header("📂 Vos vidéos générées")
    
    # Charger la galerie depuis la DB
    user_videos = get_user_videos(st.session_state['user']['id'])
    
    if user_videos:
        for video in user_videos:
            if os.path.exists(video['video_url']):
                st.sidebar.video(video['video_url'])
                st.sidebar.markdown(f"**Prompt:** {video['prompt'][:50]}...")
                st.sidebar.markdown(f"*{video['created_at']}*")
                st.sidebar.markdown("---")
    else:
        st.sidebar.info("Aucune vidéo générée pour le moment.")
    
    # Formulaire de génération
    st.markdown("### 🎨 Générer une nouvelle vidéo")
    
    uploaded_file = st.file_uploader("📷 Choisissez une image", type=["png", "jpg", "jpeg", "webp"])
    prompt = st.text_input("📝 Entrez une description pour la vidéo")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        duration = st.slider("⏱ Durée (secondes)", 2, 10, 5)
    with col2:
        resolution = st.selectbox("🎥 Résolution", ["512x512", "704x512", "1024x576"])
    
    if st.button("🚀 Générer la vidéo", use_container_width=True):
        if uploaded_file is None:
            st.error("⚠️ Veuillez sélectionner une image.")
        elif not prompt:
            st.error("⚠️ Veuillez entrer une description.")
        else:
            try:
                # Sauvegarder l'image temporairement
                with tempfile.NamedTemporaryFile(delete=False, suffix=uploaded_file.name) as tmp_file:
                    tmp_file.write(uploaded_file.read())
                    temp_path = tmp_file.name
                
                width, height = map(int, resolution.split("x"))
                
                with st.spinner("🎬 Génération en cours..."):
                    video_local_path = generate_video_with_fallback(
                        prompt=prompt,
                        image_path=temp_path,
                        width=width,
                        height=height,
                        duration=duration
                    )
                
                # Sauvegarder le vidéo localement
                unique_name = f"{uuid.uuid4().hex}.mp4"
                save_path = os.path.join(GENERATED_DIR, unique_name)
                shutil.copy(video_local_path, save_path)
                
                # Sauvegarder dans la base de données
                save_video_to_db(st.session_state['user']['id'], prompt, save_path)
                
                st.success("✅ Vidéo générée avec succès!")
                st.video(save_path)
                
                # Recharger pour afficher dans la sidebar
                st.rerun()
                
            except Exception as e:
                st.error(f"🚨 Erreur: {str(e)}")
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
else:
    st.session_state["page"] = "login"
    st.rerun()

