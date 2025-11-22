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
import requests

# ==============================================================
# CONFIG
# ==============================================================

st.set_page_config(page_title="VimeoAI - Video Generator", page_icon="🎬", layout="centered")

BASE_DIR = os.getcwd()
STATIC_DIR = os.path.join(BASE_DIR, "static")
GENERATED_DIR = os.path.join(BASE_DIR, "generated_videos")
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(GENERATED_DIR, exist_ok=True)

# Récupérer l'URL de la base de données depuis les secrets
try:
    DATABASE_URL = st.secrets["DATABASE_URL"]
except:
    # Fallback pour le développement local
    DATABASE_URL = "postgresql://neondb_owner:npg_b3qwDlLzV9YO@ep-icy-tooth-adi815w9-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"

PRIMARY_CLIENT = "Lightricks/ltx-video-distilled"
FALLBACK_CLIENT = "multimodalart/wan-2-2-first-last-frame"

# ==============================================================
# DATABASE HELPERS
# ==============================================================

def get_db_connection():
    if not DATABASE_URL:
        print("❌ DATABASE_URL not configured")
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
        return conn
    except Exception as e:
        print(f"❌ DB connection error: {e}")
        st.error(f"Erreur de connexion DB: {str(e)}")
        return None

def init_database():
    conn = get_db_connection()
    if not conn:
        print("❌ Cannot connect for DB init.")
        return
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
        print("✅ DB initialized successfully.")
    except Exception as e:
        print(f"❌ DB init error: {e}")
        try:
            conn.rollback()
        except:
            pass
        conn.close()

init_database()

# ==============================================================
# AUTH
# ==============================================================

def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def register_user(username, email, password):
    if not username or not email or not password:
        return False, "❌ Remplissez tous les champs!"
    if len(password) < 6:
        return False, "❌ Mot de passe trop court!"
    
    conn = get_db_connection()
    if not conn:
        return False, "❌ DB inaccessible"
    
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username,email,password_hash) VALUES (%s,%s,%s) RETURNING id",
            (username, email, hash_password(password))
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return True, f"✅ Compte créé (ID {user_id})"
    except psycopg2.IntegrityError:
        conn.rollback()
        conn.close()
        return False, "❌ Nom d'utilisateur ou email déjà utilisé"
    except Exception as e:
        conn.close()
        return False, str(e)

def login_user(username, password):
    conn = get_db_connection()
    if not conn:
        return None, "❌ DB inaccessible"
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT id,username,email FROM users WHERE username=%s AND password_hash=%s",
            (username, hash_password(password))
        )
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user:
            return user, "✅ Connecté"
        return None, "❌ Identifiants incorrects"
    except Exception as e:
        conn.close()
        return None, str(e)

def request_password_reset(email):
    conn = get_db_connection()
    if not conn:
        return False, "❌ DB inaccessible"
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id FROM users WHERE email=%s", (email,))
        u = cur.fetchone()
        if not u:
            cur.close()
            conn.close()
            return False, "❌ Email inconnu"
        
        token = secrets.token_urlsafe(32)
        expire = datetime.now() + timedelta(hours=1)
        cur.execute(
            "INSERT INTO user_reset_password (user_id,reset_token,expires_at) VALUES (%s,%s,%s)",
            (u['id'], token, expire)
        )
        conn.commit()
        cur.close()
        conn.close()
        return True, f"✅ Token généré: {token}"
    except Exception as e:
        conn.close()
        return False, str(e)

def reset_password(token, newpass):
    if len(newpass) < 6:
        return False, "❌ Mot de passe trop court"
    conn = get_db_connection()
    if not conn:
        return False, "❌ DB inaccessible"
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id,user_id,expires_at,used FROM user_reset_password WHERE reset_token=%s", (token,))
        r = cur.fetchone()
        if not r:
            cur.close()
            conn.close()
            return False, "❌ Token invalide"
        if r['used']:
            cur.close()
            conn.close()
            return False, "❌ Token déjà utilisé"
        if datetime.now() > r['expires_at']:
            cur.close()
            conn.close()
            return False, "❌ Token expiré"
        
        cur.execute("UPDATE users SET password_hash=%s WHERE id=%s", (hash_password(newpass), r['user_id']))
        cur.execute("UPDATE user_reset_password SET used=TRUE WHERE id=%s", (r['id'],))
        conn.commit()
        cur.close()
        conn.close()
        return True, "✅ Mot de passe réinitialisé"
    except Exception as e:
        conn.close()
        return False, str(e)

# ==============================================================
# VIDEO HELPERS
# ==============================================================

def save_video_to_db(user_id, prompt, video_path):
    """Insère une vidéo dans la DB avec debug détaillé."""
    error_msg = None
    
    print("="*60)
    print("DEBUG save_video_to_db - DÉBUT")
    print(f"  user_id: {user_id} (type: {type(user_id)})")
    print(f"  prompt: {prompt[:100]}... (len: {len(prompt)})")
    print(f"  video_path: {video_path}")
    print(f"  file exists: {os.path.exists(video_path)}")
    
    if os.path.exists(video_path):
        print(f"  file size: {os.path.getsize(video_path)} bytes")
    
    if not os.path.exists(video_path):
        error_msg = f"File does not exist: {video_path}"
        print(f"❌ ERROR: {error_msg}")
        st.error(f"🔍 ERROR: {error_msg}")
        return False
    
    print("  Tentative de connexion DB...")
    conn = get_db_connection()
    if not conn:
        error_msg = "No DB connection"
        print(f"❌ ERROR: {error_msg}")
        st.error(f"🔍 ERROR: {error_msg}")
        return False
    
    print("  Connexion DB OK")
    st.info("🔍 Connexion DB réussie")
    
    try:
        cur = conn.cursor()
        print(f"  Executing INSERT query...")
        print(f"  Query params: user_id={user_id}, prompt_len={len(prompt)}, video_path={video_path}")
        st.info(f"🔍 Exécution INSERT avec user_id={user_id}")
        
        cur.execute(
            "INSERT INTO video_generate (user_id, prompt, video_url) VALUES (%s, %s, %s) RETURNING id",
            (user_id, prompt, video_path)
        )
        
        vid_id = cur.fetchone()[0]
        print(f"  INSERT successful, video_id={vid_id}")
        st.success(f"🔍 INSERT réussi, video_id={vid_id}")
        
        conn.commit()
        print(f"  COMMIT successful")
        st.success(f"🔍 COMMIT réussi")
        
        cur.close()
        conn.close()
        
        print(f"✅ SUCCESS: Video saved to DB (id={vid_id})")
        print("="*60)
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ EXCEPTION in save_video_to_db:")
        print(f"  Error type: {type(e).__name__}")
        print(f"  Error message: {error_msg}")
        print(f"  Full traceback:")
        print(traceback.format_exc())
        
        st.error(f"🔍 ERREUR SQL: {type(e).__name__}")
        st.error(f"🔍 Message: {error_msg}")
        
        try:
            conn.rollback()
            print("  Rollback executed")
        except Exception as rb_err:
            print(f"  Rollback failed: {rb_err}")
        conn.close()
        print("="*60)
        return False

def get_user_videos(user_id, limit=50):
    conn = get_db_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT id,prompt,video_url,created_at FROM video_generate WHERE user_id=%s ORDER BY created_at DESC LIMIT %s",
            (user_id, limit)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"❌ get_user_videos error: {e}")
        conn.close()
        return []

def is_url(s):
    return isinstance(s, str) and (s.startswith('http://') or s.startswith('https://'))

def extract_video_path(result):
    """Extrait le path ou URL du résultat du client."""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for k in ['video','path','file','output','video_path','url']:
            if k in result and isinstance(result[k], str):
                return result[k]
    if isinstance(result, (list, tuple)):
        for item in result:
            p = extract_video_path(item)
            if p:
                return p
    return None

def download_video_to_path(source, dest_path, timeout=60):
    """Télécharge ou copie le fichier vidéo avec debug détaillé."""
    print("="*60)
    print("DEBUG download_video_to_path - DÉBUT")
    print(f"  source: {source}")
    print(f"  source type: {type(source)}")
    print(f"  dest_path: {dest_path}")
    
    try:
        # Cas 1: Fichier local
        if isinstance(source, str) and os.path.exists(source):
            print(f"  Mode: Copie fichier local")
            print(f"  Source exists: {os.path.exists(source)}")
            print(f"  Source size: {os.path.getsize(source)} bytes")
            
            shutil.copy2(source, dest_path)
            
            print(f"  Copie effectuée")
            print(f"  Dest exists: {os.path.exists(dest_path)}")
            print(f"  Dest size: {os.path.getsize(dest_path)} bytes")
            print(f"✅ SUCCESS: Copied local video to {dest_path}")
            print("="*60)
            return True
        
        # Cas 2: URL
        if is_url(source):
            print(f"  Mode: Téléchargement depuis URL")
            print(f"  URL: {source}")
            
            with requests.get(source, stream=True, timeout=timeout) as r:
                print(f"  HTTP Status: {r.status_code}")
                print(f"  Content-Type: {r.headers.get('content-type', 'N/A')}")
                print(f"  Content-Length: {r.headers.get('content-length', 'N/A')} bytes")
                
                if r.status_code != 200:
                    print(f"❌ ERROR: HTTP {r.status_code} during download")
                    print("="*60)
                    return False
                
                with open(dest_path, 'wb') as f:
                    total_bytes = 0
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            total_bytes += len(chunk)
                
                print(f"  Total downloaded: {total_bytes} bytes")
                print(f"  File exists: {os.path.exists(dest_path)}")
                print(f"  File size: {os.path.getsize(dest_path)} bytes")
                print(f"✅ SUCCESS: Downloaded video from URL to {dest_path}")
                print("="*60)
                return True
        
        # Cas 3: Source invalide
        print(f"❌ ERROR: Invalid video source")
        print(f"  Not a file: {not (isinstance(source, str) and os.path.exists(source))}")
        print(f"  Not a URL: {not is_url(source)}")
        print("="*60)
        return False
        
    except Exception as e:
        print(f"❌ EXCEPTION in download_video_to_path:")
        print(f"  Error type: {type(e).__name__}")
        print(f"  Error message: {str(e)}")
        print(f"  Full traceback:")
        print(traceback.format_exc())
        print("="*60)
        return False

# ==============================================================
# Génération vidéo avec fallback
# ==============================================================

def generate_video_with_fallback(prompt, image_path, width, height, duration):
    """Essaie plusieurs modèles pour générer une vidéo."""
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
            
            st.session_state['current_model'] = model_space
            st.success(f"✅ Vidéo générée avec {model_name}.")
            extracted = extract_video_path(video_result)
            print("DEBUG - extracted video path:", extracted)
            if extracted:
                return extracted
            else:
                raise ValueError("Format de résultat non reconnu: no path/url")
        
        except Exception as e:
            last_error = e
            print(f"❌ {model_name} error: {e}")
            print(traceback.format_exc())
            st.warning(f"⚠️ {model_name} non disponible: {str(e)}")
            continue
    
    raise Exception(f"❌ Tous les modèles ont échoué. Dernière erreur: {str(last_error)}")

# ==============================================================
# SESSION STATE INITIALIZATION
# ==============================================================

if 'user' not in st.session_state:
    st.session_state['user'] = None
if 'page' not in st.session_state:
    st.session_state['page'] = 'login'

# ==============================================================
# INTERFACE UTILISATEUR
# ==============================================================

def show_login_page():
    st.title("🎬 VimeoAI - Connexion")
    
    tab1, tab2, tab3 = st.tabs(["Connexion", "Inscription", "Mot de passe oublié"])
    
    with tab1:
        st.subheader("Se connecter")
        username = st.text_input("Nom d'utilisateur", key="login_username")
        password = st.text_input("Mot de passe", type="password", key="login_password")
        
        if st.button("Se connecter", type="primary"):
            user, msg = login_user(username, password)
            if user:
                st.session_state['user'] = user
                st.session_state['page'] = 'generator'
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
    
    with tab2:
        st.subheader("Créer un compte")
        new_username = st.text_input("Nom d'utilisateur", key="reg_username")
        new_email = st.text_input("Email", key="reg_email")
        new_password = st.text_input("Mot de passe", type="password", key="reg_password")
        
        if st.button("S'inscrire", type="primary"):
            success, msg = register_user(new_username, new_email, new_password)
            if success:
                st.success(msg)
                st.info("Vous pouvez maintenant vous connecter!")
            else:
                st.error(msg)
    
    with tab3:
        st.subheader("Réinitialiser le mot de passe")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Étape 1: Demander un token**")
            reset_email = st.text_input("Email", key="reset_email")
            if st.button("Envoyer le token"):
                success, msg = request_password_reset(reset_email)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
        
        with col2:
            st.write("**Étape 2: Réinitialiser**")
            reset_token = st.text_input("Token reçu", key="reset_token")
            new_pass = st.text_input("Nouveau mot de passe", type="password", key="new_pass")
            if st.button("Réinitialiser"):
                success, msg = reset_password(reset_token, new_pass)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)

def show_generator_page():
    user = st.session_state['user']
    
    st.title(f"🎬 VimeoAI - Générateur de Vidéos")
    st.write(f"Bienvenue **{user['username']}**!")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("Se déconnecter", type="secondary"):
            st.session_state['user'] = None
            st.session_state['page'] = 'login'
            st.rerun()
    
    with col2:
        if st.button("🔧 Test DB", type="secondary"):
            with st.spinner("Test de la base de données..."):
                conn = get_db_connection()
                if conn:
                    try:
                        cur = conn.cursor()
                        # Test SELECT sur la table users
                        cur.execute("SELECT COUNT(*) FROM users")
                        user_count = cur.fetchone()[0]
                        st.success(f"✅ DB OK - {user_count} utilisateurs")
                        
                        # Test SELECT sur la table video_generate
                        cur.execute("SELECT COUNT(*) FROM video_generate WHERE user_id = %s", (user['id'],))
                        video_count = cur.fetchone()[0]
                        st.info(f"📹 Vous avez {video_count} vidéos en BD")
                        
                        # Test d'insertion factice (avec rollback)
                        cur.execute("INSERT INTO video_generate (user_id, prompt, video_url) VALUES (%s, %s, %s) RETURNING id",
                                  (user['id'], "TEST", "/tmp/test.mp4"))
                        test_id = cur.fetchone()[0]
                        conn.rollback()  # On annule l'insertion
                        st.success(f"✅ Test INSERT OK (rollback effectué, test_id={test_id})")
                        
                        cur.close()
                        conn.close()
                    except Exception as e:
                        st.error(f"❌ Erreur test DB: {str(e)}")
                        st.code(traceback.format_exc())
                        conn.close()
                else:
                    st.error("❌ Impossible de se connecter à la DB")
    
    st.divider()
    
    tab1, tab2 = st.tabs(["Générer une vidéo", "Mes vidéos"])
    
    with tab1:
        st.subheader("Créer une nouvelle vidéo")
        
        prompt = st.text_area("Description de la vidéo", 
                             placeholder="Ex: Un chat qui joue avec une balle...",
                             height=100)
        
        uploaded_image = st.file_uploader("Image de départ (optionnelle)", 
                                         type=['png', 'jpg', 'jpeg'])
        
        col1, col2, col3 = st.columns(3)
        with col1:
            width = st.selectbox("Largeur", [512, 768, 1024], index=1)
        with col2:
            height = st.selectbox("Hauteur", [512, 768, 1024], index=1)
        with col3:
            duration = st.slider("Durée (secondes)", 3, 10, 5)
        
        if st.button("🎬 Générer la vidéo", type="primary"):
            if not prompt:
                st.error("Veuillez entrer une description!")
            else:
                try:
                    with st.spinner("Génération en cours..."):
                        # Sauvegarder l'image uploadée
                        if uploaded_image:
                            temp_image_path = os.path.join(STATIC_DIR, f"temp_{uuid.uuid4()}.png")
                            with open(temp_image_path, "wb") as f:
                                f.write(uploaded_image.read())
                        else:
                            # Créer une image par défaut si aucune n'est fournie
                            temp_image_path = os.path.join(STATIC_DIR, "default.png")
                            if not os.path.exists(temp_image_path):
                                st.error("Veuillez uploader une image!")
                                st.stop()
                        
                        # Générer la vidéo
                        video_path = generate_video_with_fallback(
                            prompt, temp_image_path, width, height, duration
                        )
                        
                        # Télécharger et sauvegarder la vidéo
                        final_video_path = os.path.join(GENERATED_DIR, f"video_{uuid.uuid4()}.mp4")
                        
                        st.info(f"🔍 DEBUG: Chemin vidéo extrait: {video_path}")
                        st.info(f"🔍 DEBUG: Chemin final prévu: {final_video_path}")
                        st.info(f"🔍 DEBUG: Type de video_path: {type(video_path)}")
                        
                        if download_video_to_path(video_path, final_video_path):
                            st.success(f"✅ Vidéo téléchargée vers: {final_video_path}")
                            st.info(f"🔍 DEBUG: Fichier existe? {os.path.exists(final_video_path)}")
                            st.info(f"🔍 DEBUG: Taille fichier: {os.path.getsize(final_video_path) if os.path.exists(final_video_path) else 'N/A'} bytes")
                            st.info(f"🔍 DEBUG: User ID: {user['id']}")
                            st.info(f"🔍 DEBUG: Prompt: {prompt[:50]}...")
                            
                            # Sauvegarder dans la base de données
                            save_result = save_video_to_db(user['id'], prompt, final_video_path)
                            st.info(f"🔍 DEBUG: Résultat save_video_to_db: {save_result}")
                            
                            if save_result:
                                st.success("✅ Vidéo générée et sauvegardée en BD!")
                                st.video(final_video_path)
                            else:
                                st.error("❌ Erreur lors de la sauvegarde en base de données")
                                st.error("Vérifiez les logs dans la console pour plus de détails")
                        else:
                            st.error("❌ Erreur lors du téléchargement de la vidéo")
                            st.info(f"🔍 DEBUG: download_video_to_path a retourné False")
                        
                        # Nettoyer le fichier temporaire
                        if uploaded_image and os.path.exists(temp_image_path):
                            os.remove(temp_image_path)
                
                except Exception as e:
                    st.error(f"Erreur: {str(e)}")
                    print(traceback.format_exc())
    
    with tab2:
        st.subheader("Historique de vos vidéos")
        
        videos = get_user_videos(user['id'])
        
        if not videos:
            st.info("Vous n'avez pas encore généré de vidéos.")
        else:
            for video in videos:
                with st.expander(f"📹 {video['prompt'][:50]}... ({video['created_at']})"):
                    st.write(f"**Prompt complet:** {video['prompt']}")
                    st.write(f"**Créée le:** {video['created_at']}")
                    
                    if os.path.exists(video['video_url']):
                        st.video(video['video_url'])
                    else:
                        st.warning("Vidéo non disponible localement")

# ==============================================================
# MAIN APP LOGIC
# ==============================================================

def main():
    if st.session_state['user'] is None:
        show_login_page()
    else:
        show_generator_page()

if __name__ == "__main__":
    main()
