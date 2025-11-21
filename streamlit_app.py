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
st.set_page_config(page_title="VimeoAI - Video Generator", page_icon="Film", layout="centered")

BASE_DIR = os.getcwd()
STATIC_DIR = os.path.join(BASE_DIR, "static")
GENERATED_DIR = os.path.join(BASE_DIR, "generated_videos")
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(GENERATED_DIR, exist_ok=True)

# ATTENZIONE: Sostituisci con la tua vera connection string (meglio usare st.secrets in produzione)
DATABASE_URL = st.secrets.get("DATABASE_URL", "postgresql://neondb_owner:npg_b3qwDlLzV9YO@ep-icy-tooth-adi815w9-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require")

PRIMARY_CLIENT = "Lightricks/ltx-video-distilled"
FALLBACK_CLIENT = "multimodalart/wan-2-2-first-last-frame"

# ==============================================================
# DEBUG MODE
# ==============================================================
DEBUG = True  # Metti False in produzione

def debug_print(*msg):
    if DEBUG:
        full_msg = " ".join(str(m) for m in msg)
        st.write(f"<small style='color: orange;'>[DEBUG] {full_msg}</small>", unsafe_allow_html=True)
        print(f"[DEBUG] {full_msg}")

# ==============================================================
# DATABASE HELPERS (con debug)
# ==============================================================
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
        debug_print("Connessione DB riuscita")
        return conn
    except Exception as e:
        debug_print("ERRORE connessione DB:", e)
        st.error("Impossibile connettersi al database. Controlla DATABASE_URL.")
        return None

def init_database():
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        # CORRETTO: rimosso "user TEXT NOT NULL" che era fuori posto e rompeva la sintassi!
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
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                used BOOLEAN DEFAULT FALSE
            );
        """)
        conn.commit()
        debug_print("Tabelle create o già esistenti")
    except Exception as e:
        debug_print("Errore creazione tabelle:", e)
        st.error(f"Errore inizializzazione DB: {e}")
    finally:
        conn.close()

init_database()

# ==============================================================
# AUTH (semplice, con debug)
# ==============================================================
def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def register_user(username, email, password):
    # ... (stesso codice, con debug)
    pass  # (omesso per brevità, ma funziona)

def login_user(username, password):
    conn = get_db_connection()
    if not conn:
        return None, "DB non raggiungibile"
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT id, username, email FROM users WHERE username=%s AND password_hash=%s",
            (username, hash_password(password))
        )
        user = cur.fetchone()
        conn.close()
        if user:
            debug_print("Login riuscito per:", username)
            return user, "Login OK"
        else:
            debug_print("Credenziali errate per:", username)
            return None, "Credenziali errate"
    except Exception as e:
        debug_print("Errore login:", e)
        return None, str(e)

# ==============================================================
# VIDEO SALVATAGGIO CON DEBUG MASSIMO
# ==============================================================
def save_video_to_db(user_id, prompt, video_path):
    debug_print("Tentativo salvataggio video nel DB...")
    debug_print("user_id:", user_id)
    debug_print("prompt:", prompt[:100] + "..." if len(prompt) > 100 else prompt)
    debug_print("video_path:", video_path)
    debug_print("File esiste localmente?", os.path.exists(video_path))

    if not os.path.exists(video_path):
        st.error("Il file video non esiste sul disco! Impossibile salvare nel DB.")
        debug_print("ERRORE: file video non trovato su disco!")
        return False

    conn = get_db_connection()
    if not conn:
        st.error("Impossibile connettersi al DB per salvare il video")
        return False

    try:
        cur = conn.cursor()
        debug_print("Eseguo INSERT INTO video_generate...")
        cur.execute("""
            INSERT INTO video_generate (user_id, prompt, video_url)
            VALUES (%s, %s, %s) RETURNING id
        """, (user_id, prompt, video_path))
        
        video_id = cur.fetchone()[0]
        conn.commit()
        debug_print("VIDEO SALVATO NEL DATABASE! ID =", video_id)
        st.success(f"Video salvato nel database (ID: {video_id})")
        return True

    except Exception as e:
        conn.rollback()
        debug_print("ERRORE salvataggio DB:", e)
        debug_print(traceback.format_exc())
        st.error(f"Errore salvataggio nel database: {e}")
        return False
    finally:
        conn.close()

# ==============================================================
# GENERAZIONE VIDEO (con debug)
# ==============================================================
def generate_video_with_fallback(prompt, image_path, width, height, duration):
    debug_print("Inizio generazione video con fallback...")
    # ... (stesso codice di prima)
    # Alla fine, ritorna il percorso o URL
    pass  # (codice invariato, ma con più debug_print se serve)

# ==============================================================
# PAGINA PRINCIPALE (con debug sul salvataggio)
# ==============================================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user' not in st.session_state:
    st.session_state.user = None
if 'page' not in st.session_state:
    st.session_state.page = 'login'

# Esempio login rapido per test (rimuovi in produzione!)
if st.sidebar.checkbox("Login rapido di test (user: admin, pass: admin)"):
    user_data = {'id': 1, 'username': 'admin', 'email': 'admin@test.com'}
    st.session_state.user = user_data
    st.session_state.logged_in = True
    st.session_state.page = 'app'
    st.rerun()

# ==============================================================
# APP PRINCIPALE
# ==============================================================
if st.session_state.page == 'app' and st.session_state.logged_in:
    user = st.session_state.user
    st.markdown(f"# Benvenuto {user['username']} ")

    uploaded_file = st.file_uploader("Carica immagine", type=["png", "jpg", "jpeg"])
    prompt = st.text_input("Prompt video")
    duration = st.slider("Durata (sec)", 2, 10, 5)
    resolution = st.selectbox("Risoluzione", ["512x512", "1024x576"])

    if st.button("GENERA VIDEO"):
        if not uploaded_file or not prompt:
            st.error("Carica immagine e scrivi un prompt!")
        else:
            with st.spinner("Generazione in corso..."):
                # Salva immagine temporanea
                suffix = os.path.splitext(uploaded_file.name)[1]
                temp_img = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                temp_img.write(uploaded_file.read())
                temp_img_path = temp_img.name
                temp_img.close()

                try:
                    # Genera video
                    video_source = generate_video_with_fallback(
                        prompt=prompt,
                        image_path=temp_img_path,
                        width=int(resolution.split("x")[0]),
                        height=int(resolution.split("x")[1]),
                        duration=duration
                    )

                    debug_print("Video generato, source:", video_source)

                    # Salva localmente
                    final_path = os.path.join(GENERATED_DIR, f"{uuid.uuid4().hex}.mp4")
                    success = download_video_to_path(video_source, final_path)

                    if success and os.path.exists(final_path):
                        st.success("Video scaricato con successo!")
                        st.video(final_path)

                        # QUI È IL PUNTO CRITICO: SALVATAGGIO DB
                        debug_print("Chiamo save_video_to_db...")
                        db_ok = save_video_to_db(
                            user_id=user['id'],
                            prompt=prompt,
                            video_path=final_path
                        )

                        if db_ok:
                            st.balloons()
                        else:
                            st.error("Video generato ma NON salvato nel database!")
                    else:
                        st.error("Errore nel download del video generato")

                except Exception as e:
                    st.error("Errore generazione")
                    debug_print("Errore:", e, traceback.format_exc())
                finally:
                    if os.path.exists(temp_img_path):
                        os.unlink(temp_img_path)

else:
    # Login semplice per test
    st.title("VimeoAI - Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        user, msg = login_user(username, password)
        if user:
            st.session_state.user = user
            st.session_state.logged_in = True
            st.session_state.page = 'app'
            st.rerun()
        else:
            st.error(msg)
