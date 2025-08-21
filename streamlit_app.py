import streamlit as st
import tempfile
import os
import numpy as np
from PIL import Image
import warnings
warnings.filterwarnings("ignore")

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
        background-color: #ffffff;
        color: #000000;
    }
    .stApp {
        background-color: #ffffff;
        color: #000000;
    }
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
        color: #1ab7ea;
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
    .error-box {
        background-color: #ffe6e6;
        padding: 15px;
        border-radius: 5px;
        border-left: 4px solid #ff4444;
        margin: 10px 0;
    }
    .info-box {
        background-color: #e8f4fd;
        padding: 15px;
        border-radius: 5px;
        border-left: 4px solid #1ab7ea;
        margin: 10px 0;
    }
    </style>
""", unsafe_allow_html=True)

# ---------- HEADER ----------
st.markdown("<div class='app-header'><span class='brand'>Vimeo AI</span> - Video Generator</div>", unsafe_allow_html=True)

# ---------- CHECK DEPENDENCIES ----------
def check_dependencies():
    """Vérifie si toutes les dépendances sont installées"""
    missing = []
    
    try:
        import torch
    except ImportError:
        missing.append("torch")
    
    try:
        import cv2
    except ImportError:
        missing.append("opencv-python")
    
    try:
        from diffusers import DiffusionPipeline
    except ImportError:
        missing.append("diffusers")
    
    try:
        from transformers import pipeline
    except ImportError:
        missing.append("transformers")
    
    return missing

# Vérification des dépendances
missing_deps = check_dependencies()

if missing_deps:
    st.markdown("""
    <div class='error-box'>
    ❌ <strong>Dépendances manquantes détectées :</strong><br>
    """ + ", ".join(missing_deps) + """
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class='info-box'>
    📦 <strong>Pour corriger le problème :</strong><br><br>
    
    <strong>Option 1 - Installation locale :</strong><br>
    <code>pip install torch diffusers transformers opencv-python pillow</code><br><br>
    
    <strong>Option 2 - Streamlit Cloud :</strong><br>
    Créez un fichier <code>requirements.txt</code> avec :<br>
    <pre>streamlit
torch
diffusers
transformers
opencv-python-headless
pillow
numpy
huggingface-hub</pre><br>
    
    <strong>Option 3 - Version CPU uniquement :</strong><br>
    <code>pip install torch --index-url https://download.pytorch.org/whl/cpu</code>
    </div>
    """, unsafe_allow_html=True)
    
    # Interface limitée en mode dégradé
    st.warning("⚠️ Application en mode dégradé - Fonctionnalités limitées")
    
    uploaded_file = st.file_uploader("📷 Image (non fonctionnel sans dépendances)", type=["png", "jpg", "jpeg"], disabled=True)
    prompt = st.text_input("📝 Prompt (non fonctionnel sans dépendances)", disabled=True)
    
    if st.button("🚀 Installer les dépendances d'abord", disabled=True):
        st.error("Veuillez installer les dépendances PyTorch d'abord")
    
    st.stop()

# Import des dépendances (après vérification)
import torch
import cv2
from diffusers import DiffusionPipeline
from transformers import pipeline

# ---------- CONFIGURATION ----------
STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)

@st.cache_resource
def load_model():
    """Charge le modèle avec gestion d'erreurs robuste"""
    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        
        st.info(f"🔄 Chargement du modèle sur {device.upper()}...")
        
        # Essai modèle principal
        try:
            pipe = DiffusionPipeline.from_pretrained(
                "Lightricks/ltx-video",
                torch_dtype=dtype,
                low_cpu_mem_usage=True,
                device_map="auto" if device == "cuda" else None
            )
            model_name = "LTX-Video"
        except Exception as e:
            st.warning(f"LTX-Video indisponible: {str(e)}")
            
            # Modèle de fallback
            try:
                pipe = DiffusionPipeline.from_pretrained(
                    "ali-vilab/text-to-video-ms-1.7b",
                    torch_dtype=dtype,
                    low_cpu_mem_usage=True
                )
                model_name = "Text-to-Video MS"
            except Exception as e2:
                st.error(f"Tous les modèles ont échoué: {str(e2)}")
                return None, None, device
        
        pipe = pipe.to(device)
        
        # Optimisations
        if hasattr(pipe, 'enable_memory_efficient_attention'):
            pipe.enable_memory_efficient_attention()
        if hasattr(pipe, 'enable_vae_slicing'):
            pipe.enable_vae_slicing()
            
        return pipe, model_name, device
        
    except Exception as e:
        st.error(f"❌ Erreur critique : {str(e)}")
        return None, None, "cpu"

# ---------- FONCTIONS UTILITAIRES ----------
def preprocess_image(image, target_size=(512, 512)):
    """Préprocesse l'image"""
    if isinstance(image, Image.Image):
        image = image.convert("RGB")
        image = image.resize(target_size, Image.Resampling.LANCZOS)
        return image
    return None

def generate_frames(pipe, prompt, image=None, num_frames=16, width=512, height=512, device="cpu"):
    """Génère les frames vidéo"""
    try:
        if device == "cuda":
            torch.cuda.empty_cache()
        
        with torch.no_grad():
            if image is not None:
                result = pipe(
                    prompt=prompt,
                    image=image,
                    num_frames=num_frames,
                    height=height,
                    width=width,
                    num_inference_steps=20,  # Réduit pour la vitesse
                    guidance_scale=7.5
                )
            else:
                result = pipe(
                    prompt=prompt,
                    num_frames=num_frames,
                    height=height,
                    width=width,
                    num_inference_steps=20,
                    guidance_scale=7.5
                )
        
        if hasattr(result, 'frames'):
            return result.frames[0]
        elif hasattr(result, 'videos'):
            return result.videos[0]
        return None
        
    except Exception as e:
        st.error(f"Erreur génération: {str(e)}")
        return None

def create_video(frames, output_path, fps=8):
    """Crée une vidéo à partir des frames"""
    if not frames:
        return False
    
    try:
        frame_arrays = []
        for frame in frames:
            if isinstance(frame, Image.Image):
                frame_arrays.append(np.array(frame))
        
        if not frame_arrays:
            return False
        
        height, width = frame_arrays[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        
        for frame_array in frame_arrays:
            if len(frame_array.shape) == 3:
                frame_bgr = cv2.cvtColor(frame_array, cv2.COLOR_RGB2BGR)
            else:
                frame_bgr = frame_array
            out.write(frame_bgr)
        
        out.release()
        return True
        
    except Exception as e:
        st.error(f"Erreur vidéo: {str(e)}")
        return False

# ---------- CHARGEMENT MODÈLE ----------
with st.spinner("Initialisation du modèle..."):
    pipe, model_name, device = load_model()

if pipe is None:
    st.error("❌ Impossible de charger un modèle de génération vidéo")
    st.info("💡 Vérifiez votre connexion internet et réessayez")
    st.stop()

# ---------- INFO MODÈLE ----------
st.success(f"✅ Modèle chargé: **{model_name}** sur **{device.upper()}**")

if device == "cuda":
    gpu_memory = torch.cuda.get_device_properties(0).total_memory // (1024**3)
    st.info(f"🎮 GPU détecté: {gpu_memory} GB VRAM")
else:
    st.warning("⚠️ Mode CPU: La génération sera plus lente")

# ---------- INTERFACE ----------
uploaded_file = st.file_uploader("📷 Image de départ (optionnel)", type=["png", "jpg", "jpeg"])
prompt = st.text_input("📝 Description de la vidéo", value="A beautiful landscape with moving clouds")

col1, col2 = st.columns(2)
with col1:
    num_frames = st.slider("🎞 Nombre de frames", 8, 24, 16)
with col2:
    resolution = st.selectbox("🎥 Résolution", ["512x512", "768x768", "1024x576"])

# ---------- GÉNÉRATION ----------
if st.button("🚀 Générer la vidéo"):
    if not prompt.strip():
        st.error("⚠️ Veuillez entrer une description")
    else:
        progress = st.progress(0)
        status = st.empty()
        
        try:
            # Préparation
            width, height = map(int, resolution.split("x"))
            input_image = None
            
            if uploaded_file:
                status.text("📷 Traitement image...")
                progress.progress(20)
                image = Image.open(uploaded_file)
                input_image = preprocess_image(image, (width, height))
            
            # Génération
            status.text("🎬 Génération en cours...")
            progress.progress(40)
            
            frames = generate_frames(
                pipe, prompt, input_image, 
                num_frames, width, height, device
            )
            
            if frames and len(frames) > 0:
                progress.progress(80)
                status.text("🎞 Création vidéo...")
                
                video_path = os.path.join(STATIC_DIR, "output.mp4")
                if create_video(frames, video_path):
                    progress.progress(100)
                    status.text("✅ Terminé!")
                    
                    st.success(f"🎉 Vidéo générée: {len(frames)} frames")
                    st.video(video_path)
                    
                    with open(video_path, "rb") as f:
                        st.download_button(
                            "📥 Télécharger",
                            f.read(),
                            "video.mp4",
                            "video/mp4"
                        )
                else:
                    st.error("❌ Erreur création vidéo")
            else:
                st.error("❌ Aucune frame générée")
                
        except Exception as e:
            st.error(f"🚨 Erreur: {str(e)}")
        
        finally:
            if device == "cuda":
                torch.cuda.empty_cache()

# ---------- FOOTER ----------
st.markdown("---")
st.markdown("🎬 **Vimeo AI Video Generator** - Génération vidéo IA locale", unsafe_allow_html=True)
