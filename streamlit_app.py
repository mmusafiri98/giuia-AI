import streamlit as st
import torch
import tempfile
import shutil
import os
import numpy as np
from PIL import Image
import cv2
from diffusers import DiffusionPipeline
from transformers import pipeline
import warnings
warnings.filterwarnings("ignore")

# ---------- CONFIG INTERFACE ----------
st.set_page_config(
    page_title="Vimeo AI - Video Generator (Local)",
    page_icon="🎬",
    layout="centered"
)

# ---------- CSS custom ----------
st.markdown("""
    <style>
    body {
        background-color: #ffffff;
        color: #000000;
    }
    .stApp {
        background-color: #ffffff;
        color: #000000;
    }
    /* HEADER style */
    .app-header {
        background-color: #f5f9ff;
        padding: 15px;
        text-align: left;
        font-size: 22px;
        font-weight: bold;
        color: #000000;
        border-bottom: 2px solid #dcecff;
    }
    .brand {
        color: #1ab7ea; /* bleu clair Vimeo */
    }
    .stTextInput, .stFileUploader, .stTextArea {
        background-color: #f5faff;
        color: #000000;
        border-radius: 8px;
        border: 1px solid #d0e7f7;
    }
    .stButton>button {
        background-color: #1ab7ea;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        height: 50px;
        width: 100%;
        border: none;
    }
    .stButton>button:hover {
        background-color: #18a5d5;
        color: white;
    }
    .status-info {
        background-color: #e8f4fd;
        padding: 10px;
        border-radius: 5px;
        border-left: 4px solid #1ab7ea;
        margin: 10px 0;
    }
    </style>
""", unsafe_allow_html=True)

# ---------- HEADER ----------
st.markdown("<div class='app-header'><span class='brand'>Vimeo AI</span> - Video Generator (Local)</div>", unsafe_allow_html=True)

# ---------- CONFIGURATION ----------
STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)

@st.cache_resource
def load_model():
    """Charge le modèle LTX-Video en local"""
    try:
        st.markdown("<div class='status-info'>🔄 Chargement du modèle LTX-Video... Cela peut prendre quelques minutes.</div>", unsafe_allow_html=True)
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        
        # Essai avec le modèle LTX-Video
        try:
            pipe = DiffusionPipeline.from_pretrained(
                "Lightricks/ltx-video",
                torch_dtype=dtype,
                device_map="auto" if device == "cuda" else None,
                low_cpu_mem_usage=True
            )
            pipe = pipe.to(device)
            model_name = "LTX-Video"
        except Exception as e:
            st.warning(f"⚠️ LTX-Video non disponible ({str(e)}), utilisation d'un modèle alternatif...")
            # Fallback vers un modèle plus simple
            pipe = DiffusionPipeline.from_pretrained(
                "ali-vilab/text-to-video-ms-1.7b",
                torch_dtype=dtype,
                device_map="auto" if device == "cuda" else None,
                low_cpu_mem_usage=True
            )
            pipe = pipe.to(device)
            model_name = "Text-to-Video MS"
        
        # Optimisations mémoire
        if hasattr(pipe, 'enable_memory_efficient_attention'):
            pipe.enable_memory_efficient_attention()
        if hasattr(pipe, 'enable_vae_slicing'):
            pipe.enable_vae_slicing()
        if hasattr(pipe, 'enable_sequential_cpu_offload'):
            pipe.enable_sequential_cpu_offload()
            
        return pipe, model_name, device
        
    except Exception as e:
        st.error(f"❌ Erreur lors du chargement du modèle : {str(e)}")
        return None, None, None

def preprocess_image(image, target_size=(512, 512)):
    """Préprocesse l'image pour le modèle"""
    if isinstance(image, Image.Image):
        image = image.convert("RGB")
        image = image.resize(target_size, Image.Resampling.LANCZOS)
        return image
    return None

def generate_video_frames(pipe, prompt, image=None, num_frames=16, width=512, height=512, device="cuda"):
    """Génère les frames vidéo"""
    try:
        torch.cuda.empty_cache() if device == "cuda" else None
        
        with torch.cuda.amp.autocast() if device == "cuda" else torch.no_grad():
            if image is not None:
                # Image-to-Video
                result = pipe(
                    prompt=prompt,
                    image=image,
                    num_frames=num_frames,
                    height=height,
                    width=width,
                    num_inference_steps=25,
                    guidance_scale=7.5,
                    generator=torch.Generator(device=device).manual_seed(42)
                )
            else:
                # Text-to-Video
                result = pipe(
                    prompt=prompt,
                    num_frames=num_frames,
                    height=height,
                    width=width,
                    num_inference_steps=25,
                    guidance_scale=7.5,
                    generator=torch.Generator(device=device).manual_seed(42)
                )
        
        if hasattr(result, 'frames') and result.frames is not None:
            return result.frames[0]
        elif hasattr(result, 'videos') and result.videos is not None:
            return result.videos[0]
        else:
            return None
            
    except Exception as e:
        st.error(f"❌ Erreur génération : {str(e)}")
        return None

def frames_to_video(frames, output_path, fps=8):
    """Convertit les frames en vidéo MP4"""
    try:
        if not frames:
            return False
            
        # Conversion des frames PIL en numpy
        frame_arrays = []
        for frame in frames:
            if isinstance(frame, Image.Image):
                frame_array = np.array(frame)
                frame_arrays.append(frame_array)
            elif isinstance(frame, np.ndarray):
                frame_arrays.append(frame)
        
        if not frame_arrays:
            return False
            
        # Création de la vidéo avec OpenCV
        height, width, channels = frame_arrays[0].shape
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        
        for frame_array in frame_arrays:
            # Conversion RGB -> BGR pour OpenCV
            if channels == 3:
                frame_bgr = cv2.cvtColor(frame_array, cv2.COLOR_RGB2BGR)
            else:
                frame_bgr = frame_array
            out.write(frame_bgr)
        
        out.release()
        return True
        
    except Exception as e:
        st.error(f"❌ Erreur conversion vidéo : {str(e)}")
        return False

# ---------- CHARGEMENT MODÈLE ----------
pipe, model_name, device = load_model()

if pipe is None:
    st.error("❌ Impossible de charger le modèle. Vérifiez votre installation.")
    st.stop()

# ---------- INFO SYSTÈME ----------
st.markdown(f"""
<div class='status-info'>
✅ Modèle chargé : <strong>{model_name}</strong><br>
🎮 Device : <strong>{device.upper()}</strong><br>
💾 VRAM disponible : <strong>{torch.cuda.get_device_properties(0).total_memory // 1024**3 if torch.cuda.is_available() else 'N/A'} GB</strong>
</div>
""", unsafe_allow_html=True)

# ---------- INPUTS ----------
uploaded_file = st.file_uploader("📷 Choisissez une image (optionnel pour text-to-video)", type=["png", "jpg", "jpeg"])
prompt = st.text_input("📝 Entrez une description / prompt pour la vidéo", 
                      value="A beautiful sunset over the ocean with gentle waves")

col1, col2, col3 = st.columns([1, 1, 1])
with col1:
    num_frames = st.slider("🎞 Nombre de frames", 8, 32, 16)
with col2:
    resolution = st.selectbox("🎥 Résolution", ["512x512", "704x512", "768x768"])
with col3:
    fps = st.slider("⚡ FPS", 4, 24, 8)

# ---------- GENERATE BUTTON ----------
if st.button("🚀 Générer la vidéo"):
    if not prompt:
        st.error("⚠️ Veuillez entrer une description.")
    else:
        try:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Préparation
            width, height = map(int, resolution.split("x"))
            input_image = None
            
            if uploaded_file is not None:
                status_text.text("📷 Traitement de l'image...")
                progress_bar.progress(10)
                
                image = Image.open(uploaded_file)
                input_image = preprocess_image(image, (width, height))
                mode_text = "Image-to-Video"
            else:
                mode_text = "Text-to-Video"
            
            # Génération
            status_text.text(f"🎬 Génération {mode_text}...")
            progress_bar.progress(30)
            
            frames = generate_video_frames(
                pipe=pipe,
                prompt=prompt,
                image=input_image,
                num_frames=num_frames,
                width=width,
                height=height,
                device=device
            )
            
            if frames is not None and len(frames) > 0:
                progress_bar.progress(70)
                status_text.text("🎞 Conversion en vidéo...")
                
                # Sauvegarde
                video_path = os.path.join(STATIC_DIR, "generated_video.mp4")
                if frames_to_video(frames, video_path, fps):
                    progress_bar.progress(100)
                    status_text.text("✅ Vidéo générée avec succès !")
                    
                    st.success(f"✅ Vidéo générée ! ({len(frames)} frames à {fps} FPS)")
                    st.video(video_path)
                    
                    # Bouton téléchargement
                    with open(video_path, "rb") as video_file:
                        st.download_button(
                            label="📥 Télécharger la vidéo",
                            data=video_file.read(),
                            file_name="vimeo_ai_video.mp4",
                            mime="video/mp4"
                        )
                else:
                    st.error("❌ Erreur lors de la conversion en vidéo")
            else:
                st.error("❌ Erreur lors de la génération des frames")
                
        except Exception as e:
            st.error(f"🚨 Erreur lors de la génération : {str(e)}")
            
        finally:
            # Nettoyage mémoire
            if device == "cuda":
                torch.cuda.empty_cache()

# ---------- FOOTER ----------
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; font-size: 12px;'>
🎬 Vimeo AI Video Generator - Modèle local LTX-Video<br>
⚡ Optimisé pour GPU CUDA - Compatible CPU
</div>
""", unsafe_allow_html=True)
