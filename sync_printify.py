import requests
import json
import os

# === CONFIG ===
PRINTIFY_API_KEY = os.getenv("PRINTIFY_API_TOKEN")
SHOP_ID = os.getenv("PRINTIFY_SHOP_ID")
TAGS_FILE = "product_tags.json"

def sort_option_values(option):
    name = option.get("name", "").lower()
    values = [v for v in option.get("values", []) if v.get("name")]

    if name == "size":
        size_order = ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"]
        values.sort(key=lambda v: size_order.index(v["name"]) if v["name"] in size_order else 999)
    else:
        values.sort(key=lambda v: v["name"].lower())

    return {
        "name": option.get("name"),
        "type": option.get("type"),
        "values": values
    }

# === LOAD EXISTING TAGS ===
with open(TAGS_FILE, "r") as f:
    product_tags = json.load(f)

headers = {"Authorization": f"Bearer {PRINTIFY_API_KEY}"}
updated = 0
skipped = 0

for slug, product in product_tags.items():
    pid = product.get("printify_id")
    if not pid:
        skipped += 1
        continue

    url = f"https://api.printify.com/v1/shops/{SHOP_ID}/products/{pid}.json"
    r = requests.get(url, headers=headers)

    if r.status_code != 200:
        print(f"❌ Error fetching {slug} ({pid}): {r.status_code}")
        continue

    pdata = r.json()

    # === Extract robust image list ===
    primary_images = []

    # Option 1: Extract from print_areas → placeholders → src
    for print_area in pdata.get("print_areas", []):
        for placeholder in print_area.get("placeholders", []):
            src = placeholder.get("src")
            if src:
                primary_images.append({"src": src})

    # Option 2: Fallback to top-level mockups
    if not primary_images:
        for image in pdata.get("images", []):
            src = image.get("src")
            if src:
                primary_images.append({"src": src})

    # === Filter option values to avoid blanks ===
    clean_options = [sort_option_values(opt) for opt in pdata.get("options", []) if opt.get("values")]
    for opt in pdata.get("options", []):
        values = [v for v in opt.get("values", []) if v.get("name")]
        if values:
            clean_options.append({
                "name": opt.get("name"),
                "type": opt.get("type"),
                "values": values
            })

    # === Build merged product entry ===
    enriched = {
        **product,
        "title": pdata["title"],
        "variants": pdata.get("variants", []),
        "options": clean_options,
        "images": primary_images
    }

    product_tags[slug] = enriched
    updated += 1
    print(f"✅ Updated: {slug}")

# === SAVE UPDATED FILE ===
with open(TAGS_FILE, "w") as f:
    json.dump(product_tags, f, indent=2)

print(f"\n✅ All done! {updated} updated, {skipped} skipped (no printify_id)")