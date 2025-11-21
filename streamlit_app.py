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

DATABASE_URL = "postgresql://neondb_owner:npg_b3qwDlLzV9YO@ep-icy-tooth-adi815w9-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"
PRIMARY_CLIENT = "Lightricks/ltx-video-distilled"
FALLBACK_CLIENT = "multimodalart/wan-2-2-first-last-frame"

# ==============================================================
# DATABASE HELPERS
# ==============================================================
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
        print("✅ DB connection established")
        return conn
    except Exception as e:
        print(f"❌ DB connection error: {e}")
        return None

def init_database():
    conn = get_db_connection()
    if not conn:
        print("❌ Cannot connect for DB init.")
        return
    try:
        cur = conn.cursor()
        # users table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # video_generate table
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
        # user_reset_password table
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
        print("✅ DB initialized successfully")
    except Exception as e:
        print(f"❌ DB init error: {e}")
        try:
            conn.rollback()
        except:
            pass
        conn.close()

init_database()

# ==============================================================
# AUTH HELPERS
# ==============================================================
def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def register_user(username, email, password):
    if not username or not email or not password:
        return False, "❌ Remplissez tous les champs!"
    if len(password) < 6:
        return False, "❌ Mot de passe trop corto!"

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
            cur.close(); conn.close(); return False, "❌ Email inconnu"

        token = secrets.token_urlsafe(32)
        expire = datetime.now() + timedelta(hours=1)
        cur.execute(
            "INSERT INTO user_reset_password (user_id,reset_token,expires_at) VALUES (%s,%s,%s)",
            (u['id'], token, expire)
        )
        conn.commit(); cur.close(); conn.close()
        return True, f"✅ Token generato (mostrare in prod via email): {token}"
    except Exception as e:
        conn.close(); return False, str(e)

def reset_password(token, newpass):
    if len(newpass) < 6:
        return False, "❌ Mot de passe troppo corto"
    conn = get_db_connection()
    if not conn:
        return False, "❌ DB inaccessible"
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id,user_id,expires_at,used FROM user_reset_password WHERE reset_token=%s", (token,))
        r = cur.fetchone()
        if not r:
            cur.close(); conn.close(); return False, "❌ Token invalide"
        if r['used']:
            cur.close(); conn.close(); return False, "❌ Token déjà utilisé"
        if datetime.now() > r['expires_at']:
            cur.close(); conn.close(); return False, "❌ Token expiré"

        cur.execute("UPDATE users SET password_hash=%s WHERE id=%s", (hash_password(newpass), r['user_id']))
        cur.execute("UPDATE user_reset_password SET used=TRUE WHERE id=%s", (r['id'],))
        conn.commit(); cur.close(); conn.close()
        return True, "✅ Mot de passe réinitialisé"
    except Exception as e:
        conn.close(); return False, str(e)

# ==============================================================
# VIDEO HELPERS
# ==============================================================
def save_video_to_db(user_id, prompt, video_path, image_url=None):
    """Salva il video nella tabella video_generate con debug dettagliato"""
    conn = get_db_connection()
    if not conn:
        print("❌ No DB connection for save_video_to_db")
        return False
    try:
        cur = conn.cursor()
        print(f"🔹 Saving video: user_id={user_id}, prompt='{prompt[:30]}...', video_path={video_path}")
        cur.execute(
            "INSERT INTO video_generate (user_id, prompt, video_url, image_url) VALUES (%s, %s, %s, %s) RETURNING id",
            (user_id, prompt, video_path, image_url)
        )
        vid_id = cur.fetchone()[0]
        conn.commit()
        cur.close(); conn.close()
        print(f"✅ Video saved to DB (id={vid_id})")
        return True
    except Exception as e:
        print(f"❌ save_video_to_db error: {e}")
        print(traceback.format_exc())
        try: conn.rollback()
        except: pass
        conn.close()
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
        rows = cur.fetchall(); cur.close(); conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"❌ get_user_videos error: {e}")
        conn.close(); return []

def is_url(s):
    return isinstance(s, str) and (s.startswith('http://') or s.startswith('https://'))

def extract_video_path(result):
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
    try:
        if isinstance(source, str) and os.path.exists(source):
            shutil.copy2(source, dest_path)
            return True
        if is_url(source):
            with requests.get(source, stream=True, timeout=timeout) as r:
                if r.status_code != 200:
                    print(f"❌ HTTP {r.status_code} durante download video")
                    return False
                with open(dest_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            return True
        print("❌ Source non valida per il download:", source)
        return False
    except Exception as e:
        print("❌ Exception download_video_to_path:", e)
        print(traceback.format_exc())
        return False

def generate_video_with_fallback(prompt, image_path, width, height, duration):
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
            print("DEBUG - extracted:", extracted)
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
# STREAMLIT SESSION INIT
# ==============================================================
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'user' not in st.session_state: st.session_state['user'] = None
if 'current_model' not in st.session_state: st.session_state['current_model'] = PRIMARY_CLIENT
if 'page' not in st.session_state: st.session_state['page'] = 'login'
if 'last_generated_video' not in st.session_state: st.session_state['last_generated_video'] = None

def logout():
    st.session_state['logged_in'] = False
    st.session_state['user'] = None
    st.session_state['page'] = 'login'
    st.session_state['last_generated_video'] = None
    st.rerun()
