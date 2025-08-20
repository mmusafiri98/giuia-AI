import streamlit as st
from gradio_client import Client, handle_file
import tempfile
import shutil
import os

# ---------- CONFIG INTERFACE ----------
st.set_page_config(
    page_title="Vimeo AI - Video Generator",
    page_icon="🎬",
    layout="centered"
)

# ---------- CSS custom ----------
st.markdown("""
    <style>
    body {
        background-color: #0d0d0d;
        color: white;
    }
    .stApp {
        background-color: #0d0d0d;
        color: white;
    }
    /* HEADER style */
    .app-header {
        background-color: #000;
        padding: 15px;
        text-align: left;
        font-size: 22px;
        font-weight: bold;
        color: white;
        border-bottom: 1px solid #222;
    }
    .brand {
        color: #1ab7ea; /* bleu Vimeo */
    }
    .stTextInput, .stFileUploader, .stTextArea {
        background-color: #1a1a1a;
        color: white;
        border-radius: 8px;
    }
    .stButton>button {
        background-color: #1ab7ea;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        height: 50px;
        width: 100%;
    }
    .stButton>button:hover {
        background-color: #18a5d5;
        color: white;
    }
    </style>
""", unsafe_allow_html=True)

# ---------- HEADER ----------
st.markdown("<div class='app-header'><span class='brand'>Vimeo AI</span> - Video Generator</div>", unsafe_allow_html=True)

# ---------- INITIALISATION ----------
client = Client("Lightricks/ltx-video-distilled")
STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)

# ---------- INPUTS ----------
uploaded_file = st.file_uploader("📷 Choisissez une image", type=["png", "jpg", "jpeg"])
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
        st.error("⚠️ Veuillez entrer une description.")
    else:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=uploaded_file.name) as tmp_file:
                tmp_file.write(uploaded_file.read())
                temp_path = tmp_file.name

            width, height = map(int, resolution.split("x"))

            result, seed = client.predict(
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

            if isinstance(result, dict) and "video" in result:
                video_local_path = result["video"]
                video_static_path = os.path.join(STATIC_DIR, "output.mp4")
                shutil.copy(video_local_path, video_static_path)

                st.success("✅ Vidéo générée avec succès !")
                st.video(video_static_path)
            else:
                st.error(f"❌ Erreur inattendue : {result}")

        except Exception as e:
            st.error(f"🚨 Erreur lors de la génération : {str(e)}")
