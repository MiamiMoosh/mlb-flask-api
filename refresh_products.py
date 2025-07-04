import json
import requests
from datetime import datetime, timedelta
from time import sleep

SHOP_ID = os.getenv("PRINTIFY_SHOP_ID")
API_TOKEN = os.getenv("PRINTIFY_API_TOKEN")
TAG_FILE = "product_tags.json"

with open(TAG_FILE) as f:
    data = json.load(f)

cleaned = {}
for slug, product in data.items():
    pid = product.get("printify_id")
    if not pid:
        print(f"🗑️ Skipping demo or orphaned product: {slug}")
        continue

    print(f"🔄 Rehydrating {slug} ({pid})")
    url = f"https://api.printify.com/v1/shops/{SHOP_ID}/products/{pid}.json"
    r = requests.get(url, headers={"Authorization": f"Bearer {API_TOKEN}"})
    if r.status_code != 200:
        print(f"❌ Failed to fetch {pid}: {r.status_code}")
        continue

    pdata = r.json()
    product["title"] = pdata.get("title")
    product["variants"] = pdata.get("variants", [])
    product["images"] = [{"src": i["src"]} for i in pdata.get("images", []) if i.get("src")]
    product["hydrated_at"] = datetime.utcnow().isoformat()
    cleaned[slug] = product

    sleep(0.5)  # Avoid rate limiting

with open(TAG_FILE, "w") as f:
    json.dump(cleaned, f, indent=2)

print(f"✅ Refreshed {len(cleaned)} products.")