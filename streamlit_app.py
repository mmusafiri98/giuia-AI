import streamlit as st
from gradio_client import Client, handle_file
import tempfile
import shutil
import os

# ---------- CONFIG ----------
st.set_page_config(page_title="Vimeo AI - Video Generator", page_icon="🎬", layout="centered")
STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)

# ---------- CLIENTS ----------
video_client = Client("Lightricks/ltx-video-distilled")
tts_client = Client("MohamedRashad/Multilingual-TTS")

# ---------- ONGLETS ----------
tab1, tab2 = st.tabs(["🎥 Video", "🗣 Transcript"])

# ---------- TAB VIDEO ----------
with tab1:
    uploaded_file = st.file_uploader("📷 Choisissez une image", type=["png", "jpg", "jpeg"])
    prompt = st.text_input("📝 Entrez une description / prompt pour la vidéo")
    col1, col2 = st.columns([1, 1])
    with col1:
        duration = st.slider("⏱ Durée de la vidéo (sec)", 2, 10, 5)
    with col2:
        resolution = st.selectbox("🎥 Résolution", ["512x512", "704x512", "1024x576"])

# ---------- TAB TRANSCRIPT ----------
with tab2:
    transcript_text = st.text_area("📝 Entrez le texte que le modèle doit lire dans la vidéo")
    transcript_language = st.selectbox("🌐 Langue du texte", ["French", "English", "Spanish", "Arabic"])

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

            video_local_path = video_result["video"]
            st.success("✅ Vidéo générée avec succès !")

            # ---- TTS GENERATION ----
            if transcript_text:
                speakers_data, _ = tts_client.predict(
                    language=transcript_language,
                    api_name="/get_speakers"
                )
                speaker = speakers_data["value"]

                _, audio_path = tts_client.predict(
                    text=transcript_text,
                    language_code=transcript_language,
                    speaker=speaker,
                    tashkeel_checkbox=False,
                    api_name="/text_to_speech_edge"
                )

                st.success("🎤 Audio généré avec succès !")

                # ---- AFFICHAGE SIMULTANÉ ----
                col_video, col_audio = st.columns([1, 1])
                with col_video:
                    st.video(video_local_path)
                with col_audio:
                    st.audio(audio_path)

            else:
                st.video(video_local_path)

        except Exception as e:
            st.error(f"🚨 Erreur lors de la génération : {str(e)}")
