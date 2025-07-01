import json

# Load the original product_tags.json
with open("product_tags.json", "r") as f:
    data = json.load(f)

# Build a new dictionary using slug as the key
new_data = {}
for product_id, meta in data.items():
    slug = meta.get("slug")
    if not slug:
        print(f"Skipping {product_id} — no slug")
        continue
    new_data[slug] = meta

# Optional: write to a new file (to be safe)
with open("product_tags_by_slug.json", "w") as f:
    json.dump(new_data, f, indent=2)

print("Migration complete — saved as product_tags_by_slug.json")