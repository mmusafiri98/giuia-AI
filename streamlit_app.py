import streamlit as st
from diffusers import DiffusionPipeline
import torch
import tempfile

st.set_page_config(page_title="Local AI Video Generator", layout="centered")
st.title("🎬 Generatore Video Locale (Modelscope)")

prompt = st.text_area("Prompt:", "A cute cat running in the grass")

if st.button("Genera Video"):
    with st.spinner("Caricamento modello... (può richiedere tempo al primo avvio)"):
        pipe = DiffusionPipeline.from_pretrained(
            "damo-vilab/modelscope-text-to-video-synthesis",
            torch_dtype=torch.float16,
            variant="fp16"
        ).to("cuda")

    with st.spinner("Generazione video..."):
        video_frames = pipe(prompt, num_inference_steps=25).frames

        # Salva video mp4 temporaneo
        import imageio
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        imageio.mimwrite(temp_file.name, video_frames, fps=8)

        st.success("✅ Video generato")
        st.video(temp_file.name)
