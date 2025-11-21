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
from datetime import datetime, timedelta
import traceback

# ===================================================================
# Configuration
# ===================================================================
st.set_page_config(page_title="VimeoAI - Video Generator", page_icon="🎬", layout="centered")

STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)
GENERATED_DIR = "generated_videos"
os.makedirs(GENERATED_DIR, exist_ok=True)

DATABASE_URL = "postgresql://neondb_owner:npg_b3qwDlLzV9YO@ep-icy-tooth-adi815w9-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"

PRIMARY_CLIENT = "Lightricks/ltx-video-distilled"
FALLBACK_CLIENT = "multimodalart/wan-2-2-first-last-frame"

# ===================================================================
# Database helpers
# ===================================================================
def get_db_connection():
    """Connexion à PostgreSQL (Neon)"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"❌ Erreur connexion DB: {e}")
        return None

def init_database():
    """Créer les tables si elles n'existent pas"""
    conn = get_db_connection()
    if not conn:
        print("❌ Impossible de se connecter à la DB pour init.")
        return False
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS video_generate (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                prompt TEXT NOT NULL,
                image_url TEXT,
                video_url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_reset_password (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                reset_token VARCHAR(255) NOT NULL,
                expires_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP + INTERVAL '1 hour'),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                used BOOLEAN DEFAULT FALSE
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("✅ DB initialisée.")
        return True
    except Exception as e:
        print(f"❌ Erreur init DB: {e}")
        try:
            conn.rollback()
        except:
            pass
        if conn:
            conn.close()
        return False

init_database()

# ===================================================================
# Utilitaires & Auth
# ===================================================================
def hash_password(password: str) -> str:
    """Hash password simple SHA256"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def register_user(username, email, password):
    """Enregistrer un nouvel utilisateur"""
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
        return True, f"✅ Inscription réussie! (ID {user_id})"
    except psycopg2.IntegrityError:
        try:
            conn.rollback()
        except:
            pass
        if conn:
            conn.close()
        return False, "❌ Ce nom d'utilisateur ou email existe déjà!"
    except Exception as e:
        if conn:
            conn.close()
        return False, f"❌ Erreur: {str(e)}"

def login_user(username, password):
    """Authentifier un utilisateur"""
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
            return {'id': user['id'], 'username': user['username'], 'email': user['email']}, "✅ Connexion réussie!"
        else:
            return None, "❌ Nom d'utilisateur ou mot de passe incorrect!"
    except Exception as e:
        if conn:
            conn.close()
        return None, f"❌ Erreur: {str(e)}"

def request_password_reset(email):
    """Générer un token de reset"""
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
        return True, f"✅ Token généré: `{reset_token}` (valide 1 heure)"
    except Exception as e:
        if conn:
            conn.close()
        return False, f"❌ Erreur: {str(e)}"

def reset_password(reset_token, new_password):
    """Réinitialiser mot de passe"""
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
        password_hash = hash_password(new_password)
        cur.execute("UPDATE users SET password_hash = %s WHERE id = %s",
                    (password_hash, rec['user_id']))
        cur.execute("UPDATE user_reset_password SET used = TRUE WHERE id = %s",
                    (rec['id'],))
        conn.commit()
        cur.close()
        conn.close()
        return True, "✅ Mot de passe réinitialisé avec succès!"
    except Exception as e:
        if conn:
            conn.close()
        return False, f"❌ Erreur: {str(e)}"

# ===================================================================
# Video functions
# ===================================================================
def save_video_to_db(user_id, prompt, video_path):
    """Insérer la vidéo dans la table video_generate"""
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO video_generate (user_id, prompt, video_url) VALUES (%s, %s, %s)",
            (user_id, prompt, video_path)
        )
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ Video salvata in DB: {video_path}")
        return True
    except Exception as e:
        if conn:
            conn.close()
        print(f"❌ Erreur save_video_to_db: {e}")
        return False

def get_user_videos(user_id, limit=50):
    """Récupérer vidéos d'un user"""
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
        if conn:
            conn.close()
        print(f"❌ Erreur get_user_videos: {e}")
        return []

def extract_video_path(result):
    """Estrae il path del video dal risultato dell'API"""
    print(f"🔍 Tipo risultato: {type(result)}")
    print(f"🔍 Contenuto risultato: {result}")
    
    # Caso 1: è già una stringa (path)
    if isinstance(result, str):
        if os.path.exists(result):
            print(f"✅ Path diretto trovato: {result}")
            return result
        print(f"⚠️ Path non esiste: {result}")
        return None
    
    # Caso 2: è un dizionario
    if isinstance(result, dict):
        # Prova varie chiavi comuni
        for key in ['video', 'path', 'file', 'output', 'video_path']:
            if key in result:
                path = result[key]
                if isinstance(path, str) and os.path.exists(path):
                    print(f"✅ Path trovato in dict['{key}']: {path}")
                    return path
        print(f"⚠️ Nessun path valido trovato nel dict")
        return None
    
    # Caso 3: è una tupla
    if isinstance(result, tuple):
        for i, item in enumerate(result):
            print(f"🔍 Elemento tupla [{i}]: {type(item)} = {item}")
            # Prova ricorsivamente ogni elemento
            path = extract_video_path(item)
            if path:
                return path
        print(f"⚠️ Nessun path valido trovato nella tupla")
        return None
    
    # Caso 4: è una lista
    if isinstance(result, list):
        for i, item in enumerate(result):
            print(f"🔍 Elemento lista [{i}]: {type(item)} = {item}")
            path = extract_video_path(item)
            if path:
                return path
        print(f"⚠️ Nessun path valido trovato nella lista")
        return None
    
    print(f"❌ Tipo di risultato non gestito: {type(result)}")
    return None

def generate_video_with_fallback(prompt, image_path, width, height, duration):
    """Tenta il modèle primary, puis fallback en cas d'erreur"""
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
                video_result = client.predict(
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
            else:
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

            # Estrai il path del video
            video_path = extract_video_path(video_result)
            
            if video_path and os.path.exists(video_path):
                st.session_state["current_model"] = model_space
                st.success(f"✅ Vidéo générée avec {model_name}.")
                return video_path
            else:
                raise ValueError(f"Path video non valido o file non trovato: {video_path}")
                
        except Exception as e:
            last_error = e
            error_msg = str(e)
            print(f"❌ Errore con {model_name}: {error_msg}")
            print(traceback.format_exc())
            st.warning(f"⚠️ {model_name} non disponible: {error_msg}")
            continue
    
    raise Exception(f"❌ Tous les modèles ont échoué. Dernière erreur: {str(last_error)}")

# ===================================================================
# Streamlit session state init
# ===================================================================
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "user" not in st.session_state:
    st.session_state["user"] = None
if "current_model" not in st.session_state:
    st.session_state["current_model"] = PRIMARY_CLIENT
if "page" not in st.session_state:
    st.session_state["page"] = "login"
if "last_generated_video" not in st.session_state:
    st.session_state["last_generated_video"] = None

# ===================================================================
# Logout helper
# ===================================================================
def logout():
    st.session_state["logged_in"] = False
    st.session_state["user"] = None
    st.session_state["page"] = "login"
    st.session_state["last_generated_video"] = None
    st.rerun()

# ===================================================================
# Pages rendering
# ===================================================================
def render_login():
    st.markdown("<h1 style='text-align: center; color: #4B0082;'>🔐 VimeoAI - Connexion</h1>", unsafe_allow_html=True)
    username = st.text_input("Nom d'utilisateur", key="login_username")
    password = st.text_input("Mot de passe", type="password", key="login_password")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Se connecter", use_container_width=True, key="btn_login"):
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
        if st.button("Créer un compte", use_container_width=True, key="btn_goto_register"):
            st.session_state["page"] = "register"
            st.rerun()

    if st.button("Mot de passe oublié?", key="btn_goto_forgot"):
        st.session_state["page"] = "forgot_password"
        st.rerun()

def render_register():
    st.markdown("<h1 style='text-align: center; color: #4B0082;'>📝 Créer un compte</h1>", unsafe_allow_html=True)
    new_username = st.text_input("Nom d'utilisateur", key="reg_username")
    new_email = st.text_input("Email", key="reg_email")
    new_password = st.text_input("Mot de passe", type="password", key="reg_password")
    confirm_password = st.text_input("Confirmer le mot de passe", type="password", key="reg_confirm_password")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("S'inscrire", use_container_width=True, key="btn_register"):
            if new_password != confirm_password:
                st.error("❌ Les mots de passe ne correspondent pas!")
            else:
                success, message = register_user(new_username, new_email, new_password)
                if success:
                    st.success(message)
                    st.info("Vous pouvez maintenant vous connecter.")
                    st.session_state["page"] = "login"
                    st.rerun()
                else:
                    st.error(message)
    with col2:
        if st.button("Retour", use_container_width=True, key="btn_register_back"):
            st.session_state["page"] = "login"
            st.rerun()

def render_forgot_password():
    st.markdown("<h1 style='text-align: center; color: #4B0082;'>🔑 Réinitialiser le mot de passe</h1>", unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["Demander un token", "Réinitialiser avec token"])

    with tab1:
        email = st.text_input("Votre email pour recevoir le token", key="forgot_email")
        if st.button("Envoyer le token", key="btn_send_token"):
            success, message = request_password_reset(email)
            if success:
                st.success(message)
            else:
                st.error(message)

    with tab2:
        reset_token = st.text_input("Token de réinitialisation", key="reset_token")
        new_pass = st.text_input("Nouveau mot de passe", type="password", key="reset_new_pass")
        confirm_pass = st.text_input("Confirmer le mot de passe", type="password", key="reset_confirm_pass")
        if st.button("Réinitialiser", key="btn_reset_password"):
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

    if st.button("Retour à la connexion", key="btn_back_to_login"):
        st.session_state["page"] = "login"
        st.rerun()

def render_app():
    user = st.session_state.get("user")
    if not user:
        st.session_state["page"] = "login"
        st.rerun()
        return

    st.markdown("<h1 style='text-align: center; color: #4B0082;'>🎬 VimeoAI</h1>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align: center; color: #666;'>Bienvenue **{user['username']}**!</p>", unsafe_allow_html=True)

    model_names = {
        PRIMARY_CLIENT: "LTX Video",
        FALLBACK_CLIENT: "Wan 2.2 First-Last Frame"
    }
    current_model_name = model_names.get(st.session_state["current_model"], "Inconnu")
    st.info(f"🤖 Modèle actif: **{current_model_name}**")

    # Sidebar
    st.sidebar.header(f"👤 {user['username']}")
    if st.sidebar.button("🔒 Déconnexion", key="sidebar_logout"):
        logout()

    st.sidebar.markdown("---")
    st.sidebar.header("📂 Vos vidéos générées")

    user_videos = get_user_videos(user['id'])
    if user_videos:
        for video in user_videos:
            if video.get('video_url') and os.path.exists(video['video_url']):
                with st.sidebar:
                    st.video(video['video_url'])
                    st.markdown(f"**Prompt:** {video['prompt'][:50]}...")
                    st.markdown(f"*{video['created_at']}*")
                    st.markdown("---")
            else:
                st.sidebar.warning(f"⚠️ Vidéo listée mais fichier manquant: {video.get('video_url', 'N/A')}")
    else:
        st.sidebar.info("Aucune vidéo générée pour le moment.")

    st.markdown("### 🎨 Générer une nouvelle vidéo")
    
    # Mostra l'ultimo video generato se esiste
    if st.session_state.get("last_generated_video") and os.path.exists(st.session_state["last_generated_video"]):
        st.success("✅ Dernière vidéo générée:")
        st.video(st.session_state["last_generated_video"])
        st.markdown("---")
    
    uploaded_file = st.file_uploader("📷 Choisissez une image", type=["png", "jpg", "jpeg", "webp"], key="upload_img")
    prompt = st.text_input("📝 Entrez une description pour la vidéo", key="video_prompt")

    col1, col2 = st.columns([1, 1])
    with col1:
        duration = st.slider("⏱ Durée (secondes)", 2, 10, 5, key="video_duration")
    with col2:
        resolution = st.selectbox("🎥 Résolution", ["512x512", "704x512", "1024x576"], key="video_resolution")

    if st.button("🚀 Générer la vidéo", use_container_width=True, key="btn_generate_video"):
        if uploaded_file is None:
            st.error("⚠️ Veuillez sélectionner une image.")
        elif not prompt:
            st.error("⚠️ Veuillez entrer une description.")
        else:
            temp_path = None
            try:
                # Salva temporaneamente l'immagine
                suffix = os.path.splitext(uploaded_file.name)[1] if uploaded_file.name else ".png"
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                    tmp_file.write(uploaded_file.read())
                    temp_path = tmp_file.name

                width, height = map(int, resolution.split("x"))
                
                with st.spinner("🎬 Génération en cours..."):
                    video_source_path = generate_video_with_fallback(
                        prompt=prompt,
                        image_path=temp_path,
                        width=width,
                        height=height,
                        duration=duration
                    )

                # Crea un nome unico per il video
                unique_name = f"{uuid.uuid4().hex}.mp4"
                save_path = os.path.join(GENERATED_DIR, unique_name)

                # Copia il video nella directory definitiva
                if video_source_path and os.path.exists(video_source_path):
                    print(f"📁 Copia video da {video_source_path} a {save_path}")
                    shutil.copy2(video_source_path, save_path)
                    
                    # Verifica che la copia sia andata a buon fine
                    if os.path.exists(save_path):
                        file_size = os.path.getsize(save_path)
                        print(f"✅ Video copiato con successo! Dimensione: {file_size} bytes")
                        
                        # Salva nel database
                        if save_video_to_db(user['id'], prompt, save_path):
                            st.session_state["last_generated_video"] = save_path
                            st.success("✅ Vidéo générée avec succès!")
                            st.video(save_path)
                            
                            # Ricarica la pagina per aggiornare la galleria
                            st.rerun()
                        else:
                            st.error("❌ Erreur lors de la sauvegarde dans la base de données!")
                    else:
                        st.error("❌ Erreur lors de la copie du fichier vidéo!")
                else:
                    st.error(f"❌ Fichier vidéo source invalide: {video_source_path}")

            except Exception as e:
                st.error(f"🚨 Erreur: {str(e)}")
                st.error(traceback.format_exc())
            finally:
                # Pulisci il file temporaneo
                try:
                    if temp_path and os.path.exists(temp_path):
                        os.remove(temp_path)
                        print(f"🧹 File temporaneo rimosso: {temp_path}")
                except Exception as e:
                    print(f"⚠️ Errore rimozione file temp: {e}")

# ===================================================================
# Router principale
# ===================================================================
page = st.session_state.get("page", "login")
if page == "login":
    render_login()
elif page == "register":
    render_register()
elif page == "forgot_password":
    render_forgot_password()
elif page == "app":
    render_app()
else:
    st.session_state["page"] = "login"
    render_login()
