import streamlit as st
from diffusers import StableDiffusionPipeline
import torch
import imageio
import tempfile
from PIL import Image

st.set_page_config(page_title="Generatore Immagini/Video CPU", layout="centered")
st.title("🎨 Generatore con CPU (Stable Diffusion)")

prompt = st.text_area("Prompt:", "A cute cat sitting on a chair")
frames = st.slider("Quante immagini per il video?", 4, 20, 8)

if st.button("Genera"):
    with st.spinner("Caricamento modello... (può richiedere minuti la prima volta)"):
        pipe = StableDiffusionPipeline.from_pretrained(
            "runwayml/stable-diffusion-v1-5"
        )
        pipe.to("cpu")  # Forza CPU
    
    images = []
    with st.spinner("Generazione immagini..."):
        for i in range(frames):
            image = pipe(prompt, num_inference_steps=20, guidance_scale=7.5).images[0]
            images.append(image)
    
    # Mostra prima immagine
    st.image(images[0], caption="Prima immagine generata")

    # Salva slideshow come MP4
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    imageio.mimwrite(temp_file.name, [img for img in images], fps=2)

    st.success("✅ Video generato (slideshow)")
    st.video(temp_file.name)

