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
# DATABASE
# ==============================================================
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
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
    except Exception as e:
        print(f"❌ DB init error: {e}")
        try: conn.rollback()
        except: pass
        conn.close()

init_database()

# ==============================================================
# AUTH
# ==============================================================
def hash_password(pwd): return hashlib.sha256(pwd.encode()).hexdigest()

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
        conn.commit()
        cur.close()
        conn.close()
        return True, "✅ Compte créé"
    except psycopg2.IntegrityError:
        conn.rollback()
        conn.close()
        return False, "❌ Déjà utilisé"
    except Exception as e:
        conn.close()
        return False, str(e)

def login_user(username, password):
    conn = get_db_connection()
    if not conn: return None, "❌ DB inaccessible"
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT id,username,email FROM users WHERE username=%s AND password_hash=%s",
            (username, hash_password(password))
        )
        user = cur.fetchone()
        cur.close(); conn.close()
        if user: return user, "✅ Connecté"
        return None, "❌ Identifiants incorrects"
    except Exception as e:
        conn.close(); return None, str(e)

def request_password_reset(email):
    conn = get_db_connection()
    if not conn: return False, "❌ DB inaccessible"
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
        return True, f"Token: {token}"
    except Exception as e:
        conn.close(); return False, str(e)

def reset_password(token, newpass):
    conn = get_db_connection()
    if not conn: return False, "❌ DB inaccessible"
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM user_reset_password WHERE reset_token=%s", (token,))
        r = cur.fetchone()
        if not r: return False, "❌ Token invalide"
        if r['used']: return False, "❌ Déjà utilisé"
        if datetime.now() > r['expires_at']: return False, "❌ Expiré"

        cur.execute("UPDATE users SET password_hash=%s WHERE id=%s", (hash_password(newpass), r['user_id']))
        cur.execute("UPDATE user_reset_password SET used=TRUE WHERE id=%s", (r['id'],))
        conn.commit(); cur.close(); conn.close()
        return True, "OK"
    except Exception as e:
        conn.close(); return False, str(e)

# ==============================================================
# VIDEO
# ==============================================================
def save_video_to_db(user_id, prompt, video_path):
    conn = get_db_connection()
    if not conn:
        print("❌ No DB connection for save_video_to_db")
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO video_generate (user_id,prompt,video_url) VALUES (%s,%s,%s)",
            (user_id, prompt, video_path)
        )
        conn.commit(); cur.close(); conn.close()
        print("✅ Video saved to DB")
        return True
    except Exception as e:
        print(f"❌ save_video_to_db error: {e}")
        try: conn.rollback()
        except: pass
        conn.close()
        return False

def get_user_videos(user_id, limit=30):
    conn = get_db_connection();
    if not conn: return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT * FROM video_generate WHERE user_id=%s ORDER BY created_at DESC LIMIT %s",
            (user_id, limit)
        )
        r = cur.fetchall(); cur.close(); conn.close()
        return r
    except Exception as e:
        print(e); conn.close(); return []

def extract_video_path(result):
    if isinstance(result, str) and os.path.exists(result): return result
    if isinstance(result, dict):
        for k in ["video","path","file","output","video_path"]:
            if k in result and isinstance(result[k], str) and os.path.exists(result[k]):
                return result[k]
    if isinstance(result, (list, tuple)):
        for item in result:
            p = extract_video_path(item)
            if p: return p
    return None

def generate_video_with_fallback(prompt, image_path, width, height, duration):
    models = [
        (PRIMARY_CLIENT, "LTX Video", "primary"),
        (FALLBACK_CLIENT, "WAN 2.2", "fallback")
    ]

    last_error = None
    for model, name, mode in models:
        try:
            st.info(f"🔄 {name}...")
            c = Client(model)

            if mode == "primary":
                out = c.predict(
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
                out = c.predict(
                    start_image_pil=handle_file(image_path),
                    end_image_pil=handle_file(image_path),
                    prompt=prompt,
                    duration_seconds=duration,
                    steps=8,
                    guidance_scale=1,
                    api_name="/generate_video_1"
                )

            path = extract_video_path(out)
            if path and os.path.exists(path):
                st.success(f"OK: {name}")
                return path
            else:
                raise Exception(f"Invalid video path: {path}")

        except Exception as e:
            last_error = e
            st.warning(f"⚠️ {name} fail: {e}")
            continue

    raise Exception(f"All models failed: {last_error}")

# ==============================================================
# SESSION
# ==============================================================
for key, val in {
    "logged_in": False,
    "user": None,
    "page": "login",
    "current_model": PRIMARY_CLIENT,
    "last_generated_video": None
}.items():
    if key not in st.session_state: st.session_state[key] = val

def logout():
    st.session_state.update({"logged_in": False, "user": None, "page": "login"})
    st.rerun()

# ==============================================================
# UI
# ==============================================================
def render_login():
    st.header("🔐 Connexion")
    u = st.text_input("Utilisateur")
    p = st.text_input("Mot de passe", type="password")
    if st.button("Se connecter"):
        user, msg = login_user(u, p)
        if user:
            st.session_state.logged_in = True
            st.session_state.user = user
            st.session_state.page = "app"
            st.rerun()
        else: st.error(msg)
    if st.button("Créer un compte"):
        st.session_state.page = "register"; st.rerun()
    if st.button("Mot de passe oublié"):
        st.session_state.page = "forgot"; st.rerun()

def render_register():
    st.header("Créer un compte")
    u = st.text_input("Utilisateur")
    e = st.text_input("Email")
    p = st.text_input("Mot de passe", type="password")
    c = st.text_input("Confirmer", type="password")
    if st.button("S'inscrire"):
        if p != c:
            st.error("Mismatch")
        else:
            ok, msg = register_user(u, e, p)
            if ok:
                st.success(msg); st.session_state.page = "login"; st.rerun()
            else: st.error(msg)
    if st.button("Retour"):
        st.session_state.page = "login"; st.rerun()

def render_forgot_password():
    st.header("Reset Mot de passe")
    t1, t2 = st.tabs(["Demander","Utiliser"])
    with t1:
        email = st.text_input("Email")
        if st.button("Envoyer"):
            ok, msg = request_password_reset(email)
            (st.success if ok else st.error)(msg)
    with t2:
        tok = st.text_input("Token")
        n = st.text_input("Nouveau", type="password")
        c = st.text_input("Confirmer", type="password")
        if st.button("Réinitialiser"):
            if n != c: st.error("Mismatch")
            else:
                ok, msg = reset_password(tok, n)
                if ok: st.success(msg); st.session_state.page="login"; st.rerun()
                else: st.error(msg)
    if st.button("Retour"):
        st.session_state.page="login"; st.rerun()

def render_app():
    user = st.session_state.user
    st.header("🎬 VimeoAI")
    st.sidebar.write(f"👤 {user['username']}")
    if st.sidebar.button("Déconnexion"): logout()

    vids = get_user_videos(user['id'])
    st.sidebar.subheader("Vos vidéos")
    for v in vids:
        if os.path.exists(v['video_url']): st.sidebar.video(v['video_url'])

    st.subheader("Créer une vidéo")
    img = st.file_uploader("Image",["png","jpg","jpeg","webp"])
    prompt = st.text_input("Prompt")
    duration = st.slider("Durée",2,10,5)
    res = st.selectbox("Résolution",["512x512","704x512","1024x576"])

    if st.button("Générer"):
        if not img: st.error("Choisissez une image")
        elif not prompt: st.error("Prompt vide")
        else:
            try:
                suffix = os.path.splitext(img.name)[1]
                with tempfile.NamedTemporaryFile(delete=False,suffix=suffix) as tmp:
                    tmp.write(img.read()); img_path = tmp.name
                w,h=map(int,res.split("x"))
                with st.spinner("Génération..."):
                    src = generate_video_with_fallback(prompt,img_path,w,h,duration)
                uniq = f"{uuid.uuid4().hex}.mp4"
                final = os.path.join(GENERATED_DIR,uniq)
                shutil.copy2(src, final)
                if os.path.exists(final):
                    save_video_to_db(user['id'],prompt,final)
                    st.success("Vidéo prête")
                    st.video(final)
                else: st.error("Copy fail")
            except Exception as e:
                st.error(str(e))
            finally:
                try: os.remove(img_path)
                except: pass

# ==============================================================
# ROUTER
# ==============================================================
p = st.session_state.page
if p == "login": render_login()
elif p == "register": render_register()
elif p == "forgot": render_forgot_password()
elif p == "app": render_app()
else: st.session_state.page="login"; render_login()
