import streamlit as st
from gradio_client import Client, handle_file
import tempfile
import shutil
import os
import uuid

# ---------- CONFIG ----------
st.set_page_config(page_title="VimeoAI - Video Generator", page_icon="🎬", layout="centered")

STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)
GENERATED_DIR = "generated_videos"
os.makedirs(GENERATED_DIR, exist_ok=True)

# ---------- USERS ----------
USERS = {
    "admin": "password123",
    "user": "userpass"
}

# ---------- SESSION STATE ----------
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "current_model" not in st.session_state:
    st.session_state["current_model"] = "Lightricks/ltx-video-distilled"
if "gallery" not in st.session_state:
    st.session_state["gallery"] = []

# ---------- LOGOUT ----------
def logout():
    # Resetta tutti gli stati
    st.session_state["logged_in"] = False
    st.session_state["current_model"] = "Lightricks/ltx-video-distilled"
    st.session_state["gallery"] = []
    st.success("🔒 Déconnecté avec succès !")
    st.stop()  # Blocca la sessione finché non si logga di nuovo

# ---------- LOGIN SCREEN ----------
if not st.session_state["logged_in"]:
    st.title("🔐 VimeoAI - Login")
    username = st.text_input("Nom d'utilisateur")
    password = st.text_input("Mot de passe", type="password")
    if st.button("Se connecter"):
        if USERS.get(username) == password:
            st.session_state["logged_in"] = True
            st.success(f"Bienvenue {username}!")
            st.experimental_rerun()  # Solo qui va bene
        else:
            st.error("Nom d'utilisateur ou mot de passe incorrect")
    st.stop()  # Blocca tutto finché l'utente non si logga

# ---------- CLIENTS ----------
PRIMARY_CLIENT = "Lightricks/ltx-video-distilled"
FALLBACK_CLIENT = "multimodalart/wan-2-2-first-last-frame"

# ---------- LOAD EXISTING VIDEOS ----------
for file in os.listdir(GENERATED_DIR):
    if file.endswith(".mp4"):
        video_path = os.path.join(GENERATED_DIR, file)
        if video_path not in [v["path"] for v in st.session_state["gallery"]]:
            st.session_state["gallery"].append({"path": video_path, "name": file})

# ---------- HEADER ----------
st.markdown("<h1 style='text-align: center; color: #4B0082;'>VimeoAI</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #666;'>Générez vos vidéos à partir d'une image et d'un prompt.</p>", unsafe_allow_html=True)

model_names = {
    PRIMARY_CLIENT: "LTX Video",
    FALLBACK_CLIENT: "Wan 2.2 First-Last Frame"
}
current_model_name = model_names.get(st.session_state["current_model"], "Sconosciuto")
st.info(f"🤖 Modello attivo: **{current_model_name}**")

# ---------- SIDEBAR ----------
st.sidebar.header("📂 Navigation")
if st.sidebar.button("🔒 Logout"):
    logout()

st.sidebar.header("📂 Galerie de vidéos générées")
if st.session_state["gallery"]:
    for video in st.session_state["gallery"]:
        st.sidebar.video(video["path"])
        st.sidebar.markdown(f"[⬇️ Télécharger {video['name']}]({video['path']})", unsafe_allow_html=True)
else:
    st.sidebar.info("Aucune vidéo générée pour le moment.")

# ---------- FUNCTION: GENERATE VIDEO WITH FALLBACK ----------
def generate_video_with_fallback(prompt, image_path, width, height, duration):
    models_to_try = [
        (PRIMARY_CLIENT, "LTX Video", "primary"),
        (FALLBACK_CLIENT, "Wan 2.2 First-Last Frame", "wan2.2_first_last")
    ]
    last_error = None
    for model_space, model_name, model_type in models_to_try:
        try:
            st.info(f"🔄 Tentativo con **{model_name}**...")
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
                    negative_prompt="色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量, JPEG压缩残留, 丑陋的, 残缺的, 多余的手指, 画得不好的手部, 画得不好的脸部, 畸形的, 毁容的, 形态畸形的肢体, 手指融合, 静止不动的画面, 杂乱的背景, 三条腿, 背景人很多, 倒着走, 过曝",
                    duration_seconds=duration,
                    steps=8,
                    guidance_scale=1,
                    guidance_scale_2=1,
                    seed=42,
                    randomize_seed=True,
                    api_name="/generate_video_1"
                )
            st.session_state["current_model"] = model_space
            st.success(f"✅ Video generato con successo usando **{model_name}**!")
            
            if isinstance(video_result, dict) and "video" in video_result:
                return video_result["video"]
            elif isinstance(video_result, str):
                return video_result
            elif isinstance(video_result, tuple) and len(video_result) > 0:
                return video_result[0] if isinstance(video_result[0], str) else video_result[0]["video"]
            else:
                raise ValueError(f"Formato risultato non riconosciuto: {type(video_result)}")
                
        except Exception as e:
            last_error = e
            st.warning(f"⚠️ **{model_name}** non disponibile: {str(e)}")
            continue
    
    raise Exception(f"❌ Tutti i modelli hanno fallito. Ultimo errore: {str(last_error)}")

# ---------- VIDEO FORM ----------
uploaded_file = st.file_uploader("📷 Choisissez une image", type=["png", "jpg", "jpeg","webp"])
prompt = st.text_input("📝 Entrez une description / prompt pour la vidéo")
col1, col2 = st.columns([1, 1])
with col1:
    duration = st.slider("⏱ Durée de la vidéo (sec)", 2, 10, 5)
with col2:
    resolution = st.selectbox("🎥 Résolution", ["512x512", "704x512", "1024x576"])

# ---------- GENERATE BUTTON ----------
if st.button("🚀 Générer la vidéo"):
    if uploaded_file is None:
        st.error("⚠️ Veuillez sélectionner une image.")
    elif not prompt:
        st.error("⚠️ Veuillez entrer une description pour la vidéo.")
    else:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=uploaded_file.name) as tmp_file:
                tmp_file.write(uploaded_file.read())
                temp_path = tmp_file.name

            width, height = map(int, resolution.split("x"))
            with st.spinner("🎬 Génération de la vidéo en cours..."):
                video_local_path = generate_video_with_fallback(
                    prompt=prompt,
                    image_path=temp_path,
                    width=width,
                    height=height,
                    duration=duration
                )

            unique_name = f"{uuid.uuid4().hex}.mp4"
            save_path = os.path.join(GENERATED_DIR, unique_name)
            shutil.copy(video_local_path, save_path)

            st.session_state["gallery"].append({"path": save_path, "name": unique_name})

            st.success("✅ Vidéo générée avec succès !")
            st.video(save_path)

        except Exception as e:
            st.error(f"🚨 Erreur lors de la génération : {str(e)}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)



