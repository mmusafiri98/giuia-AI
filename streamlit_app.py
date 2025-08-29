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

# ---------- CLIENT ----------
video_client = Client("Lightricks/ltx-video-distilled")

# ---------- INIT SESSION ----------
if "gallery" not in st.session_state:
    st.session_state["gallery"] = []

# ---------- LOAD EXISTING VIDEOS ----------
for file in os.listdir(GENERATED_DIR):
    if file.endswith(".mp4"):
        video_path = os.path.join(GENERATED_DIR, file)
        if video_path not in [v["path"] for v in st.session_state["gallery"]]:
            st.session_state["gallery"].append({
                "path": video_path,
                "name": file
            })

# ---------- HEADER ----------
st.markdown("<h1 style='text-align: center; color: #4B0082;'>VimeoAI</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #666;'>Générez vos vidéos à partir d'une image et d'un prompt.</p>", unsafe_allow_html=True)

# ---------- FORMULAIRE VIDEO ----------
uploaded_file = st.file_uploader("📷 Choisissez une image", type=["png", "jpg", "jpeg"])
prompt = st.text_input("📝 Entrez une description / prompt pour la vidéo")
col1, col2 = st.columns([1, 1])
with col1:
    duration = st.slider("⏱ Durée de la vidéo (sec)", 2, 10, 5)
with col2:
    resolution = st.selectbox("🎥 Résolution", ["512x512", "704x512", "1024x576"])

# ---------- SIDEBAR GALERIE ----------
st.sidebar.header("📂 Galerie de vidéos générées")
if st.session_state["gallery"]:
    for idx, video in enumerate(st.session_state["gallery"]):
        st.sidebar.video(video["path"])
        st.sidebar.markdown(f"[⬇️ Télécharger {video['name']}]({video['path']})", unsafe_allow_html=True)
else:
    st.sidebar.info("Aucune vidéo générée pour le moment.")

# ---------- GENERATE BUTTON ----------
if st.button("🚀 Générer la vidéo"):
    if uploaded_file is None:
        st.error("⚠️ Veuillez sélectionner une image.")
    elif not prompt:
        st.error("⚠️ Veuillez entrer une description pour la vidéo.")
    else:
        try:
            # ---- TEMP IMAGE ----
            with tempfile.NamedTemporaryFile(delete=False, suffix=uploaded_file.name) as tmp_file:
                tmp_file.write(uploaded_file.read())
                temp_path = tmp_file.name

            # ---- VIDEO GENERATION ----
            width, height = map(int, resolution.split("x"))
            video_result, _ = video_client.predict(
                prompt=prompt,
                input_image_filepath=handle_file(temp_path),
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

            if not (isinstance(video_result, dict) and "video" in video_result):
                st.error(f"❌ Erreur vidéo : {video_result}")
                st.stop()

            # ---- SAVE VIDEO LOCALLY ----
            video_local_path = video_result["video"]
            unique_name = f"{uuid.uuid4().hex}.mp4"
            save_path = os.path.join(GENERATED_DIR, unique_name)
            shutil.copy(video_local_path, save_path)

            # ---- UPDATE GALLERY ----
            st.session_state["gallery"].append({
                "path": save_path,
                "name": unique_name
            })

            st.success("✅ Vidéo générée avec succès !")
            st.video(save_path)

        except Exception as e:
            st.error(f"🚨 Erreur lors de la génération : {str(e)}")

