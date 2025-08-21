from diffusers import DiffusionPipeline
import torch
import imageio

if st.button("🚀 Générer la vidéo"):
    pipe = DiffusionPipeline.from_pretrained(
        "damo-vilab/text-to-video-ms-1.7b",
        torch_dtype=torch.float16
    ).to("cuda" if torch.cuda.is_available() else "cpu")
    
    with st.spinner("🎬 Génération en cours..."):
        video_frames = pipe(prompt, num_frames=duration*fps).frames

    # Sauvegarde en MP4
    output_path = "output.mp4"
    imageio.mimsave(output_path, video_frames, fps=fps)

    st.video(output_path)
    st.success("✅ Vidéo générée !")

