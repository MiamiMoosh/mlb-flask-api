import json
from slugify import slugify
from collections import defaultdict

# Load your product metadata
with open("product_tags.json", "r") as f:
    products = json.load(f)

sections = {}

# Group products by (city, sport, collection, type)
for p_id, data in products.items():
    city = data.get("city")
    sport = data.get("sport")
    collection = data.get("collection")
    type_ = data.get("type", "")  # New field
    team = data.get("team", "")
    players = data.get("players", [])  # Optional: ["Paul Skenes", "Andrew McCutchen"]

    if not (city and sport and collection and type_):
        continue

    slug = slugify(f"{city}-{sport}-{collection}-{type_}")
    team_part = f"{team} " if team else ""
    collection_name = collection.title()
    type_name = type_.title()

    # Build SEO title
    title = f"{city} {team_part}{sport.title()} {type_name} – {collection_name} Collection"

    # Base description
    description = f"Explore premium {sport.lower()} {type_.lower()}s for {city} fans. Featuring our {collection_name} Collection designed with passion and precision."

    # Add player mentions
    if players:
        joined_players = ", ".join(players)
        description += f" Includes tribute designs for {joined_players}."

    # Tag variations for SEO/ads/search matching
    keywords = [
        f"{city} {sport} {type_}",
        f"{city} {team} {type_}",
        f"{team} {sport} {type_}",
        f"{city} {sport} apparel",
        f"{city} {team} gear",
        f"{sport} gifts for {city}",
    ]

    for player in players:
        keywords.append(f"{player.lower()} {type_.lower()}")
        keywords.append(f"{player.lower()} {sport.lower()} {type_.lower()}")

    sections[slug] = {
        "title": title,
        "description": description,
        "tags": sorted(set([k.lower() for k in keywords])),
        "image": f"/static/images/seo/{slug}.jpg",
        "type": type_
    }

# Write to sections.json
with open("sections.json", "w") as f:
    json.dump(sections, f, indent=2)

print(f"Generated {len(sections)} entries to sections.json")