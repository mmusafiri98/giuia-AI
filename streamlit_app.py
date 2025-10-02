import streamlit as st
from gradio_client import Client, handle_file
import tempfile
import shutil
import os
import uuid
import time
import random

# ---------- CONFIG ----------
st.set_page_config(page_title="VimeoAI - Video Generator", page_icon="🎬", layout="centered")

STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)
GENERATED_DIR = "generated_videos"
os.makedirs(GENERATED_DIR, exist_ok=True)

# ---------- MULTIPLE SPACES CON ROTATION ----------
AVAILABLE_SPACES = [
    "Lightricks/ltx-video-distilled",
    "multimodalart/stable-video-diffusion",
    # Aggiungi altri space quando li trovi
]

# ---------- INTELLIGENT SPACE SELECTOR ----------
if "space_usage" not in st.session_state:
    st.session_state["space_usage"] = {space: {"uses": 0, "last_used": 0, "failures": 0} for space in AVAILABLE_SPACES}

def get_best_space():
    """Seleziona lo space meno utilizzato di recente"""
    current_time = time.time()
    
    # Filtra space disponibili (con meno di 3 fallimenti consecutivi)
    available = [s for s, info in st.session_state["space_usage"].items() if info["failures"] < 3]
    
    if not available:
        # Reset fallimenti se tutti sono bloccati
        for space in st.session_state["space_usage"]:
            st.session_state["space_usage"][space]["failures"] = 0
        available = AVAILABLE_SPACES
    
    # Ordina per: 1) meno fallimenti, 2) tempo dall'ultimo uso
    available.sort(key=lambda s: (
        st.session_state["space_usage"][s]["failures"],
        -abs(current_time - st.session_state["space_usage"][s]["last_used"])
    ))
    
    return available[0]

def mark_space_used(space_id, success=True):
    """Registra l'uso di uno space"""
    st.session_state["space_usage"][space_id]["uses"] += 1
    st.session_state["space_usage"][space_id]["last_used"] = time.time()
    
    if success:
        st.session_state["space_usage"][space_id]["failures"] = 0
    else:
        st.session_state["space_usage"][space_id]["failures"] += 1

# ---------- CLIENT CACHE ----------
@st.cache_resource(ttl=600)  # Cache per 10 minuti
def get_client(space_id):
    """Crea client con cache per ridurre connessioni"""
    return Client(space_id)

# ---------- INIT SESSION ----------
if "gallery" not in st.session_state:
    st.session_state["gallery"] = []

if "generation_count" not in st.session_state:
    st.session_state["generation_count"] = 0

# ---------- LOAD EXISTING VIDEOS ----------
for file in os.listdir(GENERATED_DIR):
    if file.endswith(".mp4"):
        video_path = os.path.join(GENERATED_DIR, file)
        if video_path not in [v["path"] for v in st.session_state["gallery"]]:
            st.session_state["gallery"].append({
                "path": video_path,
                "name": file
            })

# ---------- HEADER ----------
st.markdown("<h1 style='text-align: center; color: #4B0082;'>VimeoAI Pro</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #666;'>Génération vidéo optimisée avec gestion intelligente de la GPU</p>", unsafe_allow_html=True)

# ---------- GPU STATUS INDICATOR ----------
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("🎬 Vidéos générées", st.session_state["generation_count"])
with col2:
    active_spaces = sum(1 for s in st.session_state["space_usage"].values() if s["failures"] < 3)
    st.metric("🖥️ Serveurs actifs", f"{active_spaces}/{len(AVAILABLE_SPACES)}")
with col3:
    if st.session_state["generation_count"] > 0:
        avg_time = "~2 min"
    else:
        avg_time = "N/A"
    st.metric("⏱️ Temps moyen", avg_time)

# ---------- SIDEBAR ----------
st.sidebar.header("📂 Navigation")

# Info outil
with st.sidebar.expander("ℹ️ Comment ça marche?"):
    st.markdown("""
    **Optimisations GPU:**
    - 🔄 Rotation automatique entre serveurs
    - ⏰ Gestion intelligente des délais
    - 🎯 Retry automatique en cas d'erreur
    - 💾 Cache des connexions
    
    **Conseils:**
    - Utilisez des résolutions basses (512x512) pour plus de rapidité
    - Évitez les heures de pointe (14h-18h EU/US)
    - Attendez 30s entre deux générations
    """)

st.sidebar.markdown("---")
st.sidebar.markdown("**Navigation externe :**")

st.sidebar.markdown(
    """
    <a href="https://br4dskhbvzaqcdzmxgst7e.streamlit.app" target="_blank">
        <button style="background: linear-gradient(135deg,#3498db,#2980b9);
                       color:white;
                       border:none;
                       padding:10px 20px;
                       border-radius:8px;
                       font-weight:600;
                       cursor:pointer;
                       width:100%;">
            🌐 Create Video from Image with VimeoAI
        </button>
    </a>
    """,
    unsafe_allow_html=True
)

st.sidebar.markdown(
    """
    <a href="https://ntppmecv4w2uu4w9v7hxmb.streamlit.app" target="_blank">
        <button style="background: linear-gradient(135deg,#2ecc71,#27ae60);
                       color:white;
                       border:none;
                       padding:10px 20px;
                       border-radius:8px;
                       font-weight:600;
                       cursor:pointer;
                       width:100%; margin-top:10px;">
            🌐 Autre application Streamlit
        </button>
    </a>
    """,
    unsafe_allow_html=True
)

# Galerie
st.sidebar.markdown("---")
st.sidebar.header("📂 Galerie de vidéos")
if st.session_state["gallery"]:
    for idx, video in enumerate(st.session_state["gallery"]):
        with st.sidebar.expander(f"📹 Vidéo {idx+1}"):
            st.video(video["path"])
            col1, col2 = st.columns(2)
            with col1:
                with open(video["path"], "rb") as f:
                    st.download_button(
                        "⬇️ DL",
                        f,
                        file_name=video["name"],
                        mime="video/mp4",
                        key=f"dl_{video['name']}"
                    )
            with col2:
                if st.button("🗑️", key=f"del_{video['name']}"):
                    os.remove(video["path"])
                    st.session_state["gallery"].remove(video)
                    st.rerun()
else:
    st.sidebar.info("Aucune vidéo générée")

# ---------- FORMULAIRE VIDEO ----------
col1, col2 = st.columns([3, 2])

with col1:
    uploaded_file = st.file_uploader(
        "📷 Choisissez une image",
        type=["png", "jpg", "jpeg", "webp"],
        help="Formats supportés: PNG, JPG, JPEG, WEBP"
    )

with col2:
    if uploaded_file:
        st.image(uploaded_file, caption="Aperçu", use_container_width=True)

prompt = st.text_input(
    "📝 Description de la vidéo",
    placeholder="A beautiful sunset over mountains...",
    help="Description de ce que vous voulez voir dans la vidéo"
)

col1, col2 = st.columns([1, 1])
with col1:
    duration = st.slider(
        "⏱ Durée (secondes)",
        2, 10, 5,
        help="Plus court = plus rapide et moins de charge GPU"
    )
with col2:
    resolution = st.selectbox(
        "🎥 Résolution",
        ["512x512", "704x512", "1024x576"],
        help="512x512 recommandé pour rapidité et économie GPU"
    )

# Stima carico GPU
width, height = map(int, resolution.split("x"))
gpu_load = "Faible" if width <= 512 else "Moyenne" if width <= 704 else "Élevée"
gpu_color = "green" if gpu_load == "Faible" else "orange" if gpu_load == "Moyenne" else "red"

st.markdown(f"**Charge GPU estimée:** <span style='color:{gpu_color};'>■ {gpu_load}</span> | **Durée:** ~{duration * 20}-{duration * 30}s", unsafe_allow_html=True)

# ---------- GENERATE BUTTON ----------
if st.button("🚀 Générer la vidéo", type="primary", use_container_width=True):
    if uploaded_file is None:
        st.error("⚠️ Veuillez sélectionner une image.")
    elif not prompt:
        st.error("⚠️ Veuillez entrer une description pour la vidéo.")
    else:
        # Salva immagine temporanea
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
            tmp_file.write(uploaded_file.read())
            temp_path = tmp_file.name

        # Progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        max_retries = 5  # Aumentato per più resilienza
        success = False
        
        for attempt in range(max_retries):
            try:
                # Seleziona lo space migliore
                selected_space = get_best_space()
                space_name = selected_space.split("/")[-1]
                
                status_text.info(f"🔄 Tentative {attempt + 1}/{max_retries} - Serveur: {space_name}")
                progress_bar.progress(10 + (attempt * 5))
                
                # Ottieni client (cached)
                video_client = get_client(selected_space)
                
                status_text.info(f"⚙️ Génération en cours sur {space_name}... (Ne fermez pas cette page)")
                progress_bar.progress(30)
                
                # Aggiungi delay progressivo tra tentativi
                if attempt > 0:
                    delay = min(30 + (attempt * 15), 90)  # Max 90 secondi
                    status_text.warning(f"⏳ Attente de {delay}s avant nouvelle tentative...")
                    time.sleep(delay)
                
                # Genera video
                video_result, _ = video_client.predict(
                    prompt=prompt,
                    input_image_filepath=handle_file(temp_path),
                    height_ui=height,
                    width_ui=width,
                    mode="image-to-video",
                    duration_ui=duration,
                    ui_frames_to_use=9,
                    seed_ui=random.randint(0, 999999),  # Random seed per variare
                    randomize_seed=True,
                    ui_guidance_scale=1,
                    improve_texture_flag=True,
                    api_name="/image_to_video"
                )
                
                progress_bar.progress(70)

                if not (isinstance(video_result, dict) and "video" in video_result):
                    raise Exception(f"Formato risposta non valido: {video_result}")

                status_text.info("💾 Sauvegarde de la vidéo...")
                progress_bar.progress(85)
                
                # Salva video
                video_local_path = video_result["video"]
                unique_name = f"{uuid.uuid4().hex}.mp4"
                save_path = os.path.join(GENERATED_DIR, unique_name)
                shutil.copy(video_local_path, save_path)

                # Aggiorna galleria e contatori
                st.session_state["gallery"].append({
                    "path": save_path,
                    "name": unique_name
                })
                st.session_state["generation_count"] += 1
                
                # Marca space come usato con successo
                mark_space_used(selected_space, success=True)

                progress_bar.progress(100)
                status_text.success("✅ Vidéo générée avec succès!")
                
                # Mostra video
                st.video(save_path)
                
                # Download button
                with open(save_path, "rb") as f:
                    st.download_button(
                        "⬇️ Télécharger la vidéo",
                        f,
                        file_name=unique_name,
                        mime="video/mp4"
                    )
                
                success = True
                break

            except Exception as e:
                error_msg = str(e).lower()
                
                # Marca space come fallito
                mark_space_used(selected_space, success=False)
                
                # Gestione errori specifici
                if "queue" in error_msg or "busy" in error_msg or "gpu" in error_msg:
                    wait_time = 45 + (attempt * 15)
                    status_text.warning(f"⏳ GPU occupée... Attente {wait_time}s (tentative {attempt+1}/{max_retries})")
                    progress_bar.progress(min(20 + (attempt * 10), 50))
                    time.sleep(wait_time)
                    
                elif "timeout" in error_msg:
                    status_text.warning(f"⏱️ Timeout... Changement de serveur (tentative {attempt+1}/{max_retries})")
                    time.sleep(20)
                    
                elif "rate limit" in error_msg or "too many" in error_msg:
                    wait_time = 60 + (attempt * 30)
                    status_text.warning(f"🚦 Rate limit atteint... Attente {wait_time}s")
                    time.sleep(wait_time)
                    
                else:
                    status_text.error(f"⚠️ Erreur: {str(e)[:150]}")
                    if attempt < max_retries - 1:
                        time.sleep(30)
        
        # Cleanup
        try:
            os.unlink(temp_path)
        except:
            pass
        
        if not success:
            progress_bar.empty()
            status_text.error("❌ Génération échouée après plusieurs tentatives")
            st.error("""
            **🆘 Suggestions:**
            
            1. **Réessayez dans 10-15 minutes** - Les serveurs sont peut-être surchargés
            2. **Utilisez une résolution plus basse** (512x512) pour réduire la charge
            3. **Réduisez la durée** à 3-5 secondes
            4. **Essayez aux heures creuses** (nuit EU/US: 23h-7h CET)
            5. **Vérifiez votre connexion internet**
            
            💡 **Astuce:** Les serveurs gratuits sont plus disponibles la nuit!
            """)

# ---------- FOOTER ----------
st.markdown("---")
with st.expander("📊 Statistiques d'utilisation des serveurs"):
    for space_id, stats in st.session_state["space_usage"].items():
        space_name = space_id.split("/")[-1]
        status = "🟢 Actif" if stats["failures"] < 3 else "🔴 Surchargé"
        st.text(f"{status} {space_name}: {stats['uses']} utilisations, {stats['failures']} échecs")

st.markdown("""
<div style='text-align: center; color: #888; font-size: 0.85em; padding: 20px;'>
    💡 <b>Optimisations GPU:</b> Rotation automatique entre serveurs, retry intelligent, cache des connexions<br>
    ⚡ Pour de meilleures performances, utilisez 512x512 et durée 5s
</div>
""", unsafe_allow_html=True)
