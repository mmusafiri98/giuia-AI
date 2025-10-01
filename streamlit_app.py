"""
SOLUZIONE DEFINITIVA - NESSUNA DIPENDENZA COMPLESSA

Setup minimale:
1. pip install streamlit
2. pip install gradio_client
3. Run!

NO PyTorch, NO TensorFlow, NO Diffusers, NO Transformers, NO Protobuf
ZERO problemi di compatibilità!
"""

import streamlit as st
from gradio_client import Client, handle_file
import tempfile
import os
import uuid
import shutil
import time

st.set_page_config(page_title="VimeoAI Zero Dependencies", page_icon="🎬", layout="centered")

GENERATED_DIR = "generated_videos"
os.makedirs(GENERATED_DIR, exist_ok=True)

# Space HuggingFace da usare (hanno già tutto installato!)
SPACES = {
    "AnimateDiff (Veloce)": "guoyww/animatediff",
    "SVD (Stabile)": "multimodalart/stable-video-diffusion",
    "LTX (Qualità)": "Lightricks/ltx-video-distilled"
}

# ---------- SESSION STATE ----------
if "gallery" not in st.session_state:
    st.session_state["gallery"] = []

for file in os.listdir(GENERATED_DIR):
    if file.endswith(".mp4"):
        video_path = os.path.join(GENERATED_DIR, file)
        if video_path not in [v["path"] for v in st.session_state["gallery"]]:
            st.session_state["gallery"].append({"path": video_path, "name": file})

# ---------- HEADER ----------
st.markdown("""
<div style='text-align: center; padding: 30px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px; margin-bottom: 30px;'>
    <h1 style='color: white; margin: 0;'>🎬 VimeoAI</h1>
    <p style='color: #f0f0f0; margin: 10px 0 0 0;'>Aucune installation complexe requise!</p>
</div>
""", unsafe_allow_html=True)

# ---------- INFO BOX ----------
st.info("""
✅ **Cette app n'a besoin que de:**
- `pip install streamlit gradio_client`

❌ **Pas besoin de:**
- PyTorch, TensorFlow, Diffusers, Transformers, Protobuf, CUDA...
- Aucune GPU locale nécessaire!
""")

# ---------- SIDEBAR ----------
with st.sidebar:
    st.header("⚙️ Configuration")
    
    selected_model = st.selectbox(
        "🤖 Modèle",
        list(SPACES.keys()),
        help="AnimateDiff = Plus rapide, SVD = Plus stable"
    )
    
    space_id = SPACES[selected_model]
    
    st.markdown("---")
    st.header("📊 Info Modèle")
    
    if "AnimateDiff" in selected_model:
        st.success("⚡ Très rapide (~30s)")
        st.info("💾 1.7GB (léger)")
        st.warning("🎨 Qualité: ⭐⭐⭐")
    elif "SVD" in selected_model:
        st.success("⚡ Rapide (~45s)")
        st.info("💾 3.5GB")
        st.warning("🎨 Qualité: ⭐⭐⭐⭐")
    else:  # LTX
        st.warning("⏱️ Lent (~2-3min)")
        st.info("💾 8GB")
        st.success("🎨 Qualité: ⭐⭐⭐⭐⭐")
    
    st.markdown("---")
    st.header("🎨 Galerie")
    
    if st.session_state["gallery"]:
        for video in st.session_state["gallery"]:
            with st.expander(f"📹 {video['name'][:12]}..."):
                st.video(video["path"])
                col1, col2 = st.columns(2)
                with col1:
                    with open(video["path"], "rb") as f:
                        st.download_button("⬇️", f, file_name=video["name"], mime="video/mp4", key=f"dl_{video['name']}")
                with col2:
                    if st.button("🗑️", key=f"del_{video['name']}"):
                        os.remove(video["path"])
                        st.session_state["gallery"] = [v for v in st.session_state["gallery"] if v["path"] != video["path"]]
                        st.rerun()
    else:
        st.info("Aucune vidéo")

# ---------- MAIN ----------
col1, col2 = st.columns([2, 1])

with col1:
    uploaded_file = st.file_uploader(
        "📷 Choisissez une image",
        type=["png", "jpg", "jpeg", "webp"],
        help="Format supporté: PNG, JPG, JPEG, WEBP"
    )

with col2:
    if uploaded_file:
        st.image(uploaded_file, use_container_width=True)

# Parametri in base al modello
if "AnimateDiff" in selected_model or "SVD" in selected_model:
    with st.expander("⚙️ Paramètres", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            num_frames = st.slider("🎞️ Frames", 8, 24, 16)
        with col2:
            motion = st.slider("💫 Mouvement", 50, 200, 127)
    
    params = {"num_frames": num_frames, "motion": motion}
    
elif "LTX" in selected_model:
    prompt = st.text_input("📝 Description", placeholder="A beautiful landscape...")
    
    with st.expander("⚙️ Paramètres"):
        col1, col2 = st.columns(2)
        with col1:
            duration = st.slider("⏱️ Durée (sec)", 2, 10, 5)
        with col2:
            resolution = st.selectbox("📐 Résolution", ["512x512", "704x512", "1024x576"])
    
    width, height = map(int, resolution.split("x"))
    params = {"prompt": prompt or "high quality video", "duration": duration, "width": width, "height": height}

st.markdown("---")

# ---------- GENERATE ----------
if st.button("🚀 Générer la vidéo", type="primary", use_container_width=True):
    if not uploaded_file:
        st.error("⚠️ Choisissez une image d'abord")
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp.write(uploaded_file.read())
            temp_path = tmp.name

        progress = st.progress(0)
        status = st.empty()
        
        success = False
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                status.info(f"🔄 Tentative {attempt+1}/{max_retries} - Connexion à {selected_model}...")
                progress.progress(15)
                
                client = Client(space_id)
                
                status.info("⚙️ Génération en cours... Ne fermez pas cette page!")
                progress.progress(40)
                
                # Chiamata in base al modello
                if "AnimateDiff" in selected_model:
                    result = client.predict(
                        handle_file(temp_path),
                        params["num_frames"],
                        api_name="/predict"
                    )
                elif "SVD" in selected_model:
                    result = client.predict(
                        handle_file(temp_path),
                        params["num_frames"],
                        params["motion"],
                        api_name="/predict"
                    )
                else:  # LTX
                    result = client.predict(
                        prompt=params["prompt"],
                        input_image_filepath=handle_file(temp_path),
                        height_ui=params["height"],
                        width_ui=params["width"],
                        mode="image-to-video",
                        duration_ui=params["duration"],
                        ui_frames_to_use=9,
                        seed_ui=42,
                        randomize_seed=True,
                        ui_guidance_scale=1,
                        improve_texture_flag=True,
                        api_name="/image_to_video"
                    )
                
                progress.progress(85)
                status.info("💾 Sauvegarde...")
                
                # Estrai video
                if isinstance(result, tuple):
                    video_path = result[0]["video"] if isinstance(result[0], dict) else result[0]
                elif isinstance(result, dict):
                    video_path = result.get("video", result)
                else:
                    video_path = result
                
                # Salva
                unique_name = f"video_{uuid.uuid4().hex[:8]}.mp4"
                save_path = os.path.join(GENERATED_DIR, unique_name)
                shutil.copy(video_path, save_path)
                
                st.session_state["gallery"].append({"path": save_path, "name": unique_name})
                
                progress.progress(100)
                status.success("✅ Vidéo générée avec succès!")
                
                st.video(save_path)
                
                with open(save_path, "rb") as f:
                    st.download_button("⬇️ Télécharger", f, file_name=unique_name, mime="video/mp4")
                
                success = True
                break
                
            except Exception as e:
                error = str(e).lower()
                
                if "queue" in error or "busy" in error:
                    wait = 30 + (attempt * 20)
                    status.warning(f"⏳ Serveur occupé... Attente {wait}s")
                    time.sleep(wait)
                elif "timeout" in error:
                    status.warning("⏱️ Timeout, réessai...")
                    time.sleep(15)
                else:
                    status.error(f"❌ Erreur: {str(e)[:150]}")
                    time.sleep(20)
        
        if not success:
            progress.empty()
            status.error("❌ Échec après plusieurs tentatives")
            st.info("💡 Réessayez dans 5-10 minutes ou changez de modèle")
        
        try:
            os.unlink(temp_path)
        except:
            pass

# ---------- FOOTER ----------
st.markdown("---")
st.markdown("""
<div style='text-align: center; padding: 20px; background: #f8f9fa; border-radius: 10px;'>
    <h3 style='color: #666; margin: 0;'>💡 Pourquoi cette solution?</h3>
    <p style='color: #888; margin: 10px 0 0 0;'>
        Pas de PyTorch (7GB), pas de TensorFlow (500MB), pas de CUDA<br>
        Juste 2 lignes: <code>pip install streamlit gradio_client</code><br>
        Les modèles tournent sur les serveurs HuggingFace avec GPU gratuites!
    </p>
</div>
""", unsafe_allow_html=True)
