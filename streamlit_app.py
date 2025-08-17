import streamlit as st
from gradio_client import Client, handle_file
import tempfile
import shutil
import os

# Titre de l'app
st.title("Générateur de vidéos à partir d'image et prompt")

# Initialisation du client Gradio
client = Client("Lightricks/ltx-video-distilled")

# Créer un dossier temporaire pour stocker les vidéos
STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)

# Upload de l'image
uploaded_file = st.file_uploader("Choisissez une image", type=["png", "jpg", "jpeg"])
prompt = st.text_input("Description / Prompt de la vidéo")

if st.button("Générer la vidéo"):

    if uploaded_file is None:
        st.error("Veuillez sélectionner une image.")
    elif not prompt:
        st.error("Veuillez entrer une description.")
    else:
        try:
            # Sauvegarde temporaire de l'image
            with tempfile.NamedTemporaryFile(delete=False, suffix=uploaded_file.name) as tmp_file:
                tmp_file.write(uploaded_file.read())
                temp_path = tmp_file.name

            # Appel du modèle Gradio
            result, seed = client.predict(
                prompt=prompt,
                input_image_filepath=handle_file(temp_path),
                height_ui=512,
                width_ui=704,
                mode="image-to-video",
                duration_ui=2,
                ui_frames_to_use=9,
                seed_ui=42,
                randomize_seed=True,
                ui_guidance_scale=1,
                improve_texture_flag=True,
                api_name="/image_to_video"
            )

            # Récupération de la vidéo
            if isinstance(result, dict) and "video" in result:
                video_local_path = result["video"]
                video_static_path = os.path.join(STATIC_DIR, "output.mp4")
                shutil.copy(video_local_path, video_static_path)

                # Affichage de la vidéo dans Streamlit
                st.video(video_static_path)
            else:
                st.error(f"Erreur inattendue : {result}")

        except Exception as e:
            st.error(f"Erreur lors de la génération : {str(e)}")

