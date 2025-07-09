import json
import os
import mimetypes
from flask import Blueprint, render_template, request, redirect, url_for, session
from functools import wraps
from werkzeug.utils import secure_filename

admin_bp = Blueprint("admin", __name__)

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def detect_type(filename):
    ext = os.path.splitext(filename)[1].lower()
    return "video" if ext in [".mp4", ".webm", ".mov", ".m4v"] else "image"

@admin_bp.route("/admin/edit-product/<slug>", methods=["GET", "POST"])
@admin_required
def edit_product(slug):
    edits_path = f"cms_edits/{slug}.json"
    upload_dir = f"static/images/{slug}"
    os.makedirs(upload_dir, exist_ok=True)

    # Load Printify data
    with open("product_tags.json") as f:
        product_data = next((p for p in json.load(f).values() if p.get("slug") == slug), None)

    # Load existing edits
    edits = {}
    if os.path.exists(edits_path):
        with open(edits_path) as f:
            edits = json.load(f)
    else:
        edits = {"thumbnail_override": []}

    # Get available uploaded files
    available_files = os.listdir(upload_dir)

    if request.method == "POST":
        title = request.form.get("title") or ""
        desc = request.form.get("description") or ""
        font_size = request.form.get("desc_size") or "14"
        font_color = request.form.get("desc_color") or "#eee"
        sport = request.form.get("sport") or ""
        tags = request.form.get("tags").split(",") if request.form.get("tags") else []

        # Handle new file upload
        uploaded_file = request.files.get("new_media")
        if uploaded_file and uploaded_file.filename:
            filename = secure_filename(uploaded_file.filename)
            filepath = os.path.join(upload_dir, filename)
            uploaded_file.save(filepath)
            available_files.append(filename)

        thumbnails = []
        for i in range(10):
            src = request.form.get(f"src_{i}")
            poster = request.form.get(f"poster_{i}")

            file_type = detect_type(src) if src else "image"

            # Stub: Add auto-poster logic here if poster missing
            # e.g., use ffmpeg to extract first frame of video

            thumbnails.append({
                "slot": i,
                "type": file_type,
                "src": src or "",
                "poster": poster if file_type == "video" else None
            })

        new_edits = {
            "title_override": title,
            "description_override": desc,
            "description_style": {
                "font_size": int(font_size),
                "font_color": font_color
            },
            "sport_override": sport,
            "tags_override": tags,
            "thumbnail_override": thumbnails
        }

        os.makedirs("cms_edits", exist_ok=True)
        with open(edits_path, "w") as f:
            json.dump(new_edits, f, indent=2)

        return redirect(url_for("admin.edit_product", slug=slug))

    return render_template(
        "admin/edit_product.html",
        product=product_data,
        edits=edits,
        slug=slug,
        available_files=available_files,
        meta={"title": "Edit Product | First String"}
    )