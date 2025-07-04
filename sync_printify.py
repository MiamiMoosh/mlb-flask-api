import requests
import json
import os

# === CONFIG ===
PRINTIFY_API_KEY = os.getenv("PRINTIFY_API_TOKEN")
SHOP_ID = os.getenv("PRINTIFY_SHOP_ID")
TAGS_FILE = "product_tags.json"

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
    enriched = {
        **product,
        "title": pdata["title"],
        "variants": pdata["variants"],
        "options": pdata["options"],
        "images": [
            {"src": v["images"][0]["src"]}
            for v in pdata["variants"]
            if v.get("images")
        ]
    }

    product_tags[slug] = enriched
    updated += 1
    print(f"✅ Updated: {slug}")


# === SAVE UPDATED FILE ===
with open(TAGS_FILE, "w") as f:
    json.dump(product_tags, f, indent=2)

print(f"✅ Product {slug} updated in {TAGS_FILE}")

print(f"\nDone! {updated} updated, {skipped} skipped (no printify_id)")