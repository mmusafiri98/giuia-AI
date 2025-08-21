import streamlit as st
from diffusers import DiffusionPipeline
import torch
import imageio
import tempfile
import os

# ---------- CONFIG ----------
st.set_page_config(page_title="Vimeo AI - CPU Demo", page_icon="🎬", layout="centered")

st.title("🎬 Vimeo AI - Génération Vidéo (CPU Version)")

# ---------- INPUT ----------
prompt = st.text_area(
    "📝 Décris ta vidéo",
    "Un coucher de soleil sur la mer avec des vagues calmes"
)

duration = st.slider("⏱️ Durée (secondes)", 2, 6, 3)
fps = st.slider("🎞️ FPS", 4, 12, 8)

if st.button("🚀 Générer la vidéo (CPU)"):
    st.warning("⚠️ Attention : en CPU ça peut prendre plusieurs minutes...")

    # Charger le modèle (CPU uniquement)
    pipe = DiffusionPipeline.from_pretrained(
        "damo-vilab/text-to-video-ms-1.7b",
        torch_dtype=torch.float32
    ).to("cpu")

    with st.spinner("🎬 Génération en cours..."):
        video_frames = pipe(prompt, num_frames=duration * fps).frames

    # Sauvegarde en MP4
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    imageio.mimsave(tmp_file.name, video_frames, fps=fps)

    st.video(tmp_file.name)
    st.success("✅ Vidéo générée avec succès (CPU) !")
