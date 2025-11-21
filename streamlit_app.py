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
GENERATED_DIR = os.path.join(BASE_DIR, "generated_videos")
os.makedirs(GENERATED_DIR, exist_ok=True)

# Usa st.secrets in produzione! Qui per test lasciamo esplicita
DATABASE_URL = st.secrets.get("DATABASE_URL", "postgresql://neondb_owner:npg_b3qwDlLzV9YO@ep-icy-tooth-adi815w9-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require")

PRIMARY_CLIENT = "Lightricks/ltx-video-distilled"
FALLBACK_CLIENT = "multimodalart/wan-2-2-first-last-frame"

# ==============================================================
# DEBUG
# ==============================================================
def debug(*msg):
    text = " ".join(str(m) for m in msg)
    st.write(f"<small style='color:#FF9900;'><b>DEBUG:</b> {text}</small>", unsafe_allow_html=True)
    print(f"[DEBUG] {text}")

# ==============================================================
# DATABASE
# ==============================================================
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
        debug("DB connesso")
        return conn
    except Exception as e:
        debug("ERRORE DB:", e)
        st.error("Database non raggiungibile")
        return None

def init_database():
    conn = get_db_connection()
    if not conn: return
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
            CREATE TABLE IF NOT EXISTS video_generate (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                prompt TEXT NOT NULL,
                image_url TEXT,
                video_url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        debug("Tabelle pronte")
    except Exception as e:
        debug("Errore init DB:", e)
    finally:
        conn.close()

init_database()

# ==============================================================
# FUNZIONI MANCANTI (ripristinate!)
# ==============================================================
def is_url(s):
    return isinstance(s, str) and (s.startswith('http://') or s.startswith('https://'))

def extract_video_path(result):
    debug("extract_video_path riceve:", type(result), result)
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for key in ['video', 'path', 'file', 'url', 'video_path', 'output']:
            if key in result and isinstance(result[key], str):
                debug("Trovato video in chiave:", key)
                return result[key]
    if isinstance(result, (list, tuple)):
        for item in result:
            path = extract_video_path(item)
            if path: return path
    return None

def download_video_to_path(source, dest_path, timeout=90):
    debug("download_video_to_path: source =", source)
    try:
        if os.path.exists(source):
            debug("Copia file locale")
            shutil.copy2(source, dest_path)
            return True
        if is_url(source):
            debug("Scarico da URL...")
            with requests.get(source, stream=True, timeout=timeout) as r:
                r.raise_for_status()
                with open(dest_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            debug("Download completato")
            return True
        debug("Source non è né file né URL")
        return False
    except Exception as e:
        debug("ERRORE download:", e)
        return False

# ==============================================================
# GENERAZIONE VIDEO (fixato!)
# ==============================================================
def generate_video_with_fallback(prompt, image_path, width, height, duration):
    models = [
        ("Lightricks/ltx-video-distilled", "LTX Video"),
        ("multimodalart/wan-2-2-first-last-frame", "Wan2.2"),
    ]
    
    for space, name in models:
        try:
            debug(f"Tentativo con {name} ({space})")
            client = Client(space, timeout=120)

            if space == PRIMARY_CLIENT:
                result = client.predict(
                    prompt=prompt,
                    input_image_filepath=handle_file(image_path),
                    height_ui=height,
                    width_ui=width,
                    mode="image-to-video",
                    duration_ui=duration,
                    ui_frames_to_use=9,
                    seed_ui=42,
                    randomize_seed=False,
                    ui_guidance_scale=1.0,
                    improve_texture_flag=True,
                    api_name="/image_to_video"
                )
            else:
                result = client.predict(
                    start_image_pil=handle_file(image_path),
                    end_image_pil=handle_file(image_path),
                    prompt=prompt,
                    negative_prompt="blurry, low quality",
                    duration_seconds=duration,
                    steps=8,
                    guidance_scale=1.0,
                    guidance_scale_2=1.0,
                    seed=42,
                    randomize_seed=False,
                    api_name="/generate_video_1"
                )

            debug(f"Risultato grezzo da {name}:", result)
            video_path = extract_video_path(result)
            
            if video_path:
                debug(f"SUCCESSO con {name} → {video_path}")
                st.success(f"Generato con {name}")
                return video_path
            else:
                debug(f"{name} non ha restituito percorso valido")
                
        except Exception as e:
            debug(f"{name} fallito:", str(e))
            st.warning(f"{name} non disponibile")
            continue

    st.error("Tutti i modelli hanno fallito")
    return None

# ==============================================================
# SALVATAGGIO DB
# ==============================================================
def save_video_to_db(user_id, prompt, video_path):
    debug("save_video_to_db → user_id:", user_id, "path:", video_path)
    if not os.path.exists(video_path):
        st.error("File video non esiste sul disco!")
        return False

    conn = get_db_connection()
    if not conn: return False

    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO video_generate (user_id, prompt, video_url) VALUES (%s, %s, %s) RETURNING id",
            (user_id, prompt, video_path)
        )
        vid_id = cur.fetchone()[0]
        conn.commit()
        debug(f"VIDEO SALVATO NEL DB! ID = {vid_id}")
        st.success(f"Salvato nel database (ID {vid_id})")
        return True
    except Exception as e:
        conn.rollback()
        debug("ERRORE DB:", e, traceback.format_exc())
        st.error("Errore salvataggio DB")
        return False
    finally:
        conn.close()

# ==============================================================
# LOGIN SEMPLICE PER TEST
# ==============================================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user' not in st.session_state:
    st.session_state.user = None

# Login di test (rimuovi in produzione)
with st.sidebar:
    st.header("Test rapido")
    if st.button("Login come admin (test)"):
        st.session_state.user = {"id": 1, "username": "admin"}
        st.session_state.logged_in = True
        st.rerun()

# ==============================================================
# APP PRINCIPALE
# ==============================================================
if st.session_state.logged_in and st.session_state.user:
    st.title("VimeoAI - Generatore Video")
    st.write(f"**Utente:** {st.session_state.user['username']}")

    uploaded_file = st.file_uploader("Carica immagine iniziale", type=["png", "jpg", "jpeg", "webp"])
    prompt = st.text_area("Prompt per il movimento", "a beautiful sunset over mountains, cinematic, slow motion")
    col1, col2 = st.columns(2)
    with col1:
        duration = st.slider("Durata (secondi)", 3, 10, 5)
    with col2:
        res = st.selectbox("Risoluzione", ["512x512", "768x512", "1024x576"], index=1)
    w, h = map(int, res.split("x"))

    if st.button("GENERA VIDEO", type="primary", use_container_width=True):
        if not uploaded_file:
            st.error("Carica un'immagine!")
        elif not prompt.strip():
            st.error("Scrivi un prompt!")
        else:
            with st.spinner("Generazione in corso..."):
                # Salva immagine temporanea
                suffix = os.path.splitext(uploaded_file.name)[1] or ".jpg"
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                tmp.write(uploaded_file.read())
                tmp_path = tmp.name
                tmp.close()

                try:
                    video_source = generate_video_with_fallback(prompt, tmp_path, w, h, duration)

                    if not video_source:
                        st.error("Nessun modello ha funzionato")
                    else:
                        final_path = os.path.join(GENERATED_DIR, f"{uuid.uuid4().hex}.mp4")
                        if download_video_to_path(video_source, final_path):
                            st.video(final_path)
                            st.success("Video scaricato!")

                            # SALVATAGGIO NEL DB
                            if save_video_to_db(st.session_state.user["id"], prompt, final_path):
                                st.balloons()
                            else:
                                st.error("Video generato ma NON salvato nel DB")
                        else:
                            st.error("Impossibile scaricare il video")
                finally:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
else:
    st.title("VimeoAI")
    st.write("Fai login di test con il pulsante a sinistra per provare")
