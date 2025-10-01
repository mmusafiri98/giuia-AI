import streamlit as st
import time
from google import genai

# Configura client
client = genai.Client()

st.set_page_config(page_title="AI Video Generator", layout="centered")

st.title("🎬 AI Video Generator con Imagen + Veo 3")

prompt = st.text_area("Inserisci un prompt per il video:", "Panning wide shot of a calico kitten sleeping in the sunshine")

if st.button("Genera Video"):
    with st.spinner("Generazione immagine..."):
        # Step 1: Genera immagine con Imagen
        imagen = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=prompt,
        )
        img = imagen.generated_images[0].image
        st.image(img, caption="Immagine generata con Imagen")

    with st.spinner("Generazione video con Veo 3..."):
        # Step 2: Genera video con Veo
        operation = client.models.generate_videos(
            model="veo-3.0-generate-001",
            prompt=prompt,
            image=img,
        )

        # Poll finché l'operazione è completata
        while not operation.done:
            st.info("⏳ Attendi, sto generando il video...")
            time.sleep(10)
            operation = client.operations.get(operation)

        # Step 3: Scarica video
        video = operation.response.generated_videos[0]
        path = "veo3_with_image_input.mp4"
        client.files.download(file=video.video)
        video.video.save(path)

        st.success("✅ Video generato!")
        st.video(path)

