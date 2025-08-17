import os
import shutil
import tempfile
from flask import Flask, render_template, request, url_for
from werkzeug.utils import secure_filename
from gradio_client import Client, handle_file

app = Flask(__name__)
client = Client("Lightricks/ltx-video-distilled")

STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)

@app.route("/", methods=["GET", "POST"])
def index():
    video_url = None
    error_message = None

    if request.method == "POST":
        if "image" not in request.files:
            error_message = "Veuillez sélectionner une image."
        else:
            image = request.files["image"]
            description = request.form.get("description", "")

            try:
                # Sauvegarde temporaire de l'image
                filename = secure_filename(image.filename)
                temp_path = os.path.join(tempfile.gettempdir(), filename)
                image.save(temp_path)

                # Appel Gradio pour générer la vidéo
                result, seed = client.predict(
                    prompt=description,
                    input_image_filepath=handle_file(temp_path),
                    height_ui=512,
                    width_ui=704,
                    mode="image-to-video",
                    duration_ui=2,
                    ui_frames_to_use=9,
                    seed_ui=42,
                    randomize_seed=True,
                    ui_guidance_scale=1,
                    improve_texture_flag=True,
                    api_name="/image_to_video"
                )

                # Récupération de la vidéo locale
                if isinstance(result, dict) and "video" in result:
                    video_local_path = result["video"]  # chemin local
                    video_static_path = os.path.join(STATIC_DIR, "output.mp4")

                    # Copier la vidéo dans static/
                    shutil.copy(video_local_path, video_static_path)

                    # URL relative pour le navigateur
                    video_url = url_for('static', filename="output.mp4")
                else:
                    error_message = f"Erreur inattendue : {result}"

            except Exception as e:
                error_message = f"Erreur lors de la génération : {str(e)}"

    return render_template("index.html", video_url=video_url, error_message=error_message)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
