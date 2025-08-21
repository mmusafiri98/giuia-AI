import streamlit as st
from PIL import Image
import requests
import tempfile
import os
import time
import random

# ---------- CONFIG ----------
st.set_page_config(
    page_title="Vimeo AI - Video Generator",
    page_icon="🎬",
    layout="centered"
)

# ---------- CSS ----------
st.markdown("""
    <style>
    .stApp {
        background-color: #ffffff;
    }
    .app-header {
        background-color: #f5f9ff;
        padding: 20px;
        text-align: center;
        font-size: 28px;
        font-weight: bold;
        color: #000000;
        border-bottom: 3px solid #1ab7ea;
        margin-bottom: 30px;
    }
    .brand {
        color: #1ab7ea;
    }
    .demo-box {
        background-color: #e8f4fd;
        padding: 20px;
        border-radius: 10px;
        border-left: 4px solid #1ab7ea;
        margin: 20px 0;
    }
    .feature-box {
        background-color: #f0f8f0;
        padding: 15px;
        border-radius: 8px;
        border-left: 4px solid #28a745;
        margin: 10px 0;
    }
    .stButton>button {
        background-color: #1ab7ea;
        color: white;
        font-weight: bold;
        border-radius: 10px;
        height: 60px;
        width: 100%;
        font-size: 18px;
        border: none;
    }
    .stButton>button:hover {
        background-color: #18a5d5;
    }
    </style>
""", unsafe_allow_html=True)

# ---------- HEADER ----------
st.markdown("""
<div class='app-header'>
    <span class='brand'>🎬 Vimeo AI</span><br>
    <span style='font-size: 18px; color: #666;'>Video Generator</span>
</div>
""", unsafe_allow_html=True)

# ---------- DEMO MODE ----------
st.markdown("""
<div class='demo-box'>
    <h3>🚧 Version Demo - Streamlit Cloud</h3>
    <p><strong>Cette version démontre l'interface utilisateur.</strong> 
    Les modèles d'IA de génération vidéo nécessitent trop de ressources pour Streamlit Cloud.</p>
    
    <p><strong>Pour la version complète :</strong></p>
    <ul>
        <li>📱 Utilisez Google Colab (GPU gratuit)</li>
        <li>💻 Installation locale avec GPU</li>
        <li>☁️ Hugging Face Spaces</li>
    </ul>
</div>
""", unsafe_allow_html=True)

# ---------- INTERFACE COMPLÈTE ----------
col1, col2 = st.columns([1, 1])

with col1:
    st.markdown("### 📷 Image d'entrée")
    uploaded_file = st.file_uploader(
        "Choisissez une image", 
        type=["png", "jpg", "jpeg"],
        help="L'image sera utilisée comme première frame de la vidéo"
    )
    
    if uploaded_file:
        image = Image.open(uploaded_file)
        st.image(image, caption="Image uploadée", use_column_width=True)

with col2:
    st.markdown("### ⚙️ Paramètres")
    
    prompt = st.text_area(
        "📝 Description de la vidéo",
        value="A beautiful sunset over calm ocean waters with gentle waves",
        height=100,
        help="Décrivez le mouvement et l'ambiance souhaités"
    )
    
    col2_1, col2_2 = st.columns(2)
    
    with col2_1:
        duration = st.slider("⏱️ Durée (sec)", 2, 10, 5)
        resolution = st.selectbox("🎥 Résolution", [
            "512x512", "768x512", "1024x576", "1280x720"
        ])
    
    with col2_2:
        fps = st.slider("🎞️ FPS", 8, 30, 24)
        style = st.selectbox("🎨 Style", [
            "Réaliste", "Cinématique", "Artistique", "Animation"
        ])

# ---------- PARAMÈTRES AVANCÉS ----------
with st.expander("🔧 Paramètres avancés"):
    col3_1, col3_2, col3_3 = st.columns(3)
    
    with col3_1:
        guidance_scale = st.slider("🎯 Guidance Scale", 1.0, 20.0, 7.5)
        num_inference_steps = st.slider("🔄 Steps", 10, 50, 25)
    
    with col3_2:
        seed = st.number_input("🌱 Seed", value=42)
        randomize_seed = st.checkbox("🎲 Seed aléatoire", value=True)
    
    with col3_3:
        motion_strength = st.slider("💫 Force du mouvement", 0.1, 2.0, 1.0)
        coherence = st.slider("🔗 Cohérence temporelle", 0.1, 1.0, 0.8)

# ---------- GÉNÉRATION (DEMO) ----------
if st.button("🚀 Générer la vidéo (Demo)"):
    # Simulation de génération
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Étapes simulées
    steps = [
        ("🔄 Chargement du modèle...", 10),
        ("📷 Analyse de l'image...", 25),
        ("🧠 Traitement du prompt...", 40),
        ("🎬 Génération des frames...", 70),
        ("🎞️ Assemblage vidéo...", 90),
        ("✅ Finalisation...", 100)
    ]
    
    for step_text, progress in steps:
        status_text.text(step_text)
        progress_bar.progress(progress)
        time.sleep(0.8)  # Simulation du temps de traitement
    
    # Résultats simulés
    st.success("🎉 Vidéo générée avec succès ! (Demo)")
    
    # Affichage des paramètres utilisés
    st.markdown("### 📊 Paramètres utilisés:")
    
    col4_1, col4_2 = st.columns(2)
    
    with col4_1:
        st.markdown(f"""
        **📏 Dimensions:** {resolution}  
        **⏱️ Durée:** {duration}s  
        **🎞️ FPS:** {fps}  
        **🎨 Style:** {style}
        """)
    
    with col4_2:
        st.markdown(f"""
        **🎯 Guidance:** {guidance_scale}  
        **🔄 Steps:** {num_inference_steps}  
        **🌱 Seed:** {seed if not randomize_seed else random.randint(1, 10000)}  
        **💫 Motion:** {motion_strength}
        """)
    
    # Message pour la vraie version
    st.markdown("""
    <div class='demo-box'>
        <h4>🎬 Résultat attendu :</h4>
        <p>Dans la version complète, vous obtiendriez ici :</p>
        <ul>
            <li>📹 Vidéo MP4 de {duration} secondes</li>
            <li>⬇️ Bouton de téléchargement</li>
            <li>👁️ Prévisualisation intégrée</li>
            <li>📈 Métriques de qualité</li>
        </ul>
    </div>
    """.format(duration=duration), unsafe_allow_html=True)

# ---------- INSTRUCTIONS INSTALLATION ----------
st.markdown("---")
st.markdown("## 🛠️ Installation de la version complète")

tab1, tab2, tab3 = st.tabs(["💻 Local", "📱 Google Colab", "☁️ Hugging Face"])

with tab1:
    st.markdown("""
    ### Installation locale
    ```bash
    # 1. Cloner le repo
    git clone https://github.com/votre-repo/vimeo-ai
    cd vimeo-ai
    
    # 2. Installer les dépendances
    pip install torch diffusers transformers streamlit pillow opencv-python
    
    # 3. Lancer l'app
    streamlit run streamlit_app_full.py
    ```
    
    **Requis:** GPU avec 8GB+ VRAM recommandé
    """)

with tab2:
    st.markdown("""
    ### Google Colab (Gratuit + GPU)
    ```python
    # Dans un notebook Colab :
    !git clone https://github.com/votre-repo/vimeo-ai
    %cd vimeo-ai
    !pip install -r requirements.txt
    
    # Lancer avec tunnel public
    !streamlit run app.py & npx localtunnel --port 8501
    ```
    
    **Avantages:** GPU T4 gratuit, installation facile
    """)

with tab3:
    st.markdown("""
    ### Hugging Face Spaces
    
    1. **Fork le repo** sur Hugging Face Spaces
    2. **Sélectionnez** : Python + Streamlit + GPU
    3. **Uploadez** les fichiers `app.py` et `requirements.txt`
    4. **Attendez** le déploiement automatique
    
    **Coût:** ~$0.60/heure pour GPU
    """)

# ---------- EXEMPLES ----------
st.markdown("---")
st.markdown("## 🎨 Exemples de prompts")

examples = [
    {
        "prompt": "Un coucher de soleil doré sur un lac paisible avec des reflets scintillants",
        "style": "Cinématique",
        "description": "Mouvements fluides de l'eau, lumière changeante"
    },
    {
        "prompt": "Des nuages qui bougent rapidement dans un ciel bleu éclatant",
        "style": "Réaliste", 
        "description": "Time-lapse naturel, mouvement accéléré"
    },
    {
        "prompt": "Une forêt enchantée avec des particules magiques flottantes",
        "style": "Artistique",
        "description": "Ambiance féerique, effets de lumière"
    },
    {
        "prompt": "Une ville futuriste avec des voitures volantes",
        "style": "Animation",
        "description": "Sci-fi, mouvements dynamiques"
    }
]

for i, example in enumerate(examples):
    with st.expander(f"💡 Exemple {i+1}: {example['style']}"):
        st.markdown(f"""
        **Prompt:** {example['prompt']}  
        **Style:** {example['style']}  
        **Description:** {example['description']}
        """)

# ---------- FOOTER ----------
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 20px;'>
    <p><strong>🎬 Vimeo AI Video Generator</strong></p>
    <p>Version Demo pour Streamlit Cloud | 
    <a href="#" style="color: #1ab7ea;">Documentation</a> | 
    <a href="#" style="color: #1ab7ea;">GitHub</a> | 
    <a href="#" style="color: #1ab7ea;">Support</a></p>
</div>
""", unsafe_allow_html=True)
