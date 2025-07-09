import json
import os

from flask import Blueprint, render_template, request, redirect, url_for, session
from functools import wraps

admin_bp = Blueprint("admin", __name__)
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

@admin_bp.route("/admin/edit-product/<slug>", methods=["GET", "POST"])
@admin_required
def edit_product(slug):
    edits_path = f"cms_edits/{slug}.json"

    # Load Printify data
    with open("product_tags.json") as f:
        product_data = next((p for p in json.load(f).values() if p.get("slug") == slug), None)

    # Load existing edits
    edits = {}
    if os.path.exists(edits_path):
        with open(edits_path) as f:
            edits = json.load(f)
    else:
        edits = {"thumbnail_override": []}  # ✅ Add a fallback

    if request.method == "POST":
        # Handle uploads and metadata
        title = request.form.get("title") or ""
        desc = request.form.get("description") or ""
        font_size = request.form.get("desc_size") or "14"
        font_color = request.form.get("desc_color") or "#eee"
        sport = request.form.get("sport") or ""
        tags = request.form.get("tags").split(",") if request.form.get("tags") else []

        thumbnails = []
        for i in range(10):
            thumb_type = request.form.get(f"type_{i}")
            src = request.form.get(f"src_{i}")
            poster = request.form.get(f"poster_{i}") if thumb_type == "video" else None
            if src:
                thumbnails.append({
                    "slot": i,
                    "type": thumb_type,
                    "src": src,
                    "poster": poster
                })

        new_edits = {
            "title_override": title,
            "description_override": desc,
            "description_style": { "font_size": int(font_size), "font_color": font_color },
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
        meta={"title": "Edit Product | First String"}
    )
