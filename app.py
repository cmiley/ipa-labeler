from flask import Flask, render_template, request, jsonify, send_from_directory, send_file
from werkzeug.utils import secure_filename
from pathlib import Path
import io
import json
import os
import shutil
import threading
import zipfile

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".webm"}
SEED_FILES = ["harvard.wav"]

app = Flask(__name__)

DATA_DIR = Path(os.environ.get("IPA_LABELER_DATA_DIR", ".")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
app.config["UPLOAD_FOLDER"] = DATA_DIR / "uploads"
app.config["UPLOAD_FOLDER"].mkdir(exist_ok=True)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

annotations_file = DATA_DIR / "annotations.json"
if not annotations_file.exists():
    annotations_file.write_text("{}")

# Seed bundled sample files into UPLOAD_FOLDER on first start with a fresh volume.
_app_dir = Path(__file__).parent.resolve()
for _name in SEED_FILES:
    _src = _app_dir / _name
    _dst = app.config["UPLOAD_FOLDER"] / _name
    if _src.exists() and not _dst.exists():
        shutil.copy2(_src, _dst)

# Annotations is a single JSON file in Phase 1; serialize read-modify-write
# across request threads. Phase 2 replaces this with Postgres transactions.
_annotations_lock = threading.Lock()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/healthz")
def healthz():
    return {"ok": True}, 200


@app.route("/upload", methods=["POST"])
def upload_audio():
    if "audio" not in request.files:
        return jsonify({"error": "No file"}), 400

    file = request.files["audio"]
    if not file.filename:
        return jsonify({"error": "No filename"}), 400

    safe_name = secure_filename(file.filename)
    if not safe_name:
        return jsonify({"error": "Invalid filename"}), 400

    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Unsupported file type: {ext or '(none)'}"}), 400

    if file.mimetype and not file.mimetype.startswith("audio/"):
        return jsonify({"error": f"Unexpected MIME type: {file.mimetype}"}), 400

    filepath = app.config["UPLOAD_FOLDER"] / safe_name
    file.save(filepath)
    return jsonify({"filename": safe_name})


@app.route("/audio/<filename>")
def serve_audio(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/annotations/<filename>", methods=["GET", "POST"])
def handle_annotations(filename):
    with _annotations_lock:
        data = json.loads(annotations_file.read_text())

        if request.method == "POST":
            data[filename] = request.json
            annotations_file.write_text(json.dumps(data, indent=2))
            return jsonify({"status": "saved"})

        return jsonify(data.get(filename, []))


@app.route("/export/<filename>/<format>")
def export_annotations(filename, format):
    with _annotations_lock:
        data = json.loads(annotations_file.read_text())
    annotations = data.get(filename, [])

    if format == "json":
        output = json.dumps(annotations, indent=2)
        mimetype = "application/json"
        ext = "json"
    elif format == "txt":
        lines = []
        for ann in annotations:
            semantic = ann.get("semanticLabel", "")
            if semantic:
                lines.append(
                    f"{ann['startTime']:.2f}s - {ann['endTime']:.2f}s: {ann['text']} ({semantic})"
                )
            else:
                lines.append(f"{ann['startTime']:.2f}s - {ann['endTime']:.2f}s: {ann['text']}")
        output = "\n".join(lines)
        mimetype = "text/plain"
        ext = "txt"
    else:
        return jsonify({"error": "Invalid format"}), 400

    return send_file(
        io.BytesIO(output.encode("utf-8")),
        mimetype=mimetype,
        as_attachment=True,
        download_name=f"{Path(filename).stem}_annotations.{ext}",
    )


@app.route("/export/<filename>/zip")
def export_zip(filename, format=None):
    with _annotations_lock:
        data = json.loads(annotations_file.read_text())
    annotations = data.get(filename, [])

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        audio_path = app.config["UPLOAD_FOLDER"] / filename
        if audio_path.exists():
            zip_file.write(audio_path, filename)

        annotations_json = json.dumps(annotations, indent=2)
        zip_file.writestr(f"{Path(filename).stem}_annotations.json", annotations_json)

        lines = []
        for ann in annotations:
            semantic = ann.get("semanticLabel", "")
            if semantic:
                lines.append(
                    f"{ann['startTime']:.2f}s - {ann['endTime']:.2f}s: {ann['text']} ({semantic})"
                )
            else:
                lines.append(f"{ann['startTime']:.2f}s - {ann['endTime']:.2f}s: {ann['text']}")
        annotations_txt = "\n".join(lines)
        zip_file.writestr(f"{Path(filename).stem}_annotations.txt", annotations_txt)

    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{Path(filename).stem}_export.zip",
    )


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", "5000")))
