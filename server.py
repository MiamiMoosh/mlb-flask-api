import os
import time
import asyncio
import datetime
import pytz
from flask import Flask, jsonify, render_template, request, redirect, url_for
from datetime import date
from playwright.async_api import async_playwright
from pymongo import MongoClient

# Initialize Flask app
app = Flask(__name__, template_folder="pages")
port = int(os.environ.get("PORT", 8080))

# Connect to MongoDB using Railway-provided URI
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo:MXQDxgcJWYBgTFtLPiwGdsnRXTIONzNc@trolley.proxy.rlwy.net:25766")
client = MongoClient(MONGO_URI)
db = client["mlb_stats"]
collection = db["batter_vs_pitcher"]
streak_collection = db["hot_streak_players"]


async def scrape_all_data(date):
    # Run both scrapers concurrently
    async with asyncio.TaskGroup() as tg:
        streak_task = tg.create_task(scrape_streak_data())
        stats_task = tg.create_task(scrape_data(date))
        
        streak_data, stats_data = await asyncio.gather(streak_task, stats_task)

    return streak_data, stats_data

async def scrape_data(date):
    url = f"https://swishanalytics.com/optimus/mlb/batter-vs-pitcher-stats?date={date}"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, timeout=15000, wait_until="domcontentloaded")
        print(f"[DEBUG] Scraping data for {date} from {url}")

        try:
            await page.wait_for_selector("table tbody tr", timeout=10000)
        except Exception:
            print("[ERROR] Table not found or took too long to load!")
            return []

        rows_data = await page.eval_on_selector_all("table tbody tr", r"""
            rows => {
                const teamAbbreviations = {
                    "whitesox": "CWS", "guardians": "CLE", "tigers": "DET", "royals": "KC", "twins": "MIN",
                    "orioles": "BAL", "redsox": "BOS", "yankees": "NYY", "rays": "TB", "bluejays": "TOR",
                    "athletics": "OAK", "astros": "HOU", "angels": "LAA", "mariners": "SEA", "rangers": "TEX",
                    "cubs": "CHC", "reds": "CIN", "brewers": "MIL", "pirates": "PIT", "cardinals": "STL",
                    "braves": "ATL", "marlins": "MIA", "mets": "NYM", "phillies": "PHI", "nationals": "WAS",
                    "diamondbacks": "ARI", "rockies": "COL", "dodgers": "LAD", "padres": "SD", "giants": "SF"
                };

                return rows.map(row => {
                    let cells = row.querySelectorAll("td");
                    let teamImgs = row.querySelectorAll("td img");
                    if (cells.length < 14 || teamImgs.length < 2) return null;

                    let batterTeam = teamImgs[0]?.src?.split('/').pop().replace('.png', '').toLowerCase();
                    let pitcherTeam = teamImgs[1]?.src?.split('/').pop().replace('.png', '').toLowerCase();
                    let batterElement = cells[0]?.querySelector(".batter-name");
                    let pitcherElement = cells[1]?.querySelector(".pitcher-name");
                    let batterName = batterElement?.innerText?.trim() || "Unknown";
                    let pitcherName = pitcherElement?.innerText?.trim() || "Unknown";
                    let batterHandedness = batterElement?.nextSibling?.textContent?.trim() || "";
                    let batterPosition = batterElement?.nextSibling?.nextSibling?.textContent?.trim() || "";
                    let pitcherHandedness = pitcherElement?.nextSibling?.textContent?.trim() || "";

                    const removeNA = (text) => text.replace(/\$?N\/A/g, "").trim();
                    const fixParentheses = (text) => text.replace(/[()]+/g, "").trim();

                    batterHandedness = removeNA(batterHandedness) ? `(${fixParentheses(removeNA(batterHandedness))})` : "";
                    batterPosition = removeNA(batterPosition);
                    pitcherHandedness = removeNA(pitcherHandedness) ? `(${fixParentheses(removeNA(pitcherHandedness))})` : "";

                    return {
                        team_batter: teamAbbreviations[batterTeam] || "Unknown",
                        batter: batterName,
                        batter_info: `${batterHandedness} ${batterPosition}`.trim(),
                        team_pitcher: teamAbbreviations[pitcherTeam] || "Unknown",
                        pitcher: pitcherName,
                        pitcher_hand: pitcherHandedness,
                        stats: {
                            PA: cells[2]?.innerText?.trim(),
                            AB: cells[3]?.innerText?.trim(),
                            H: cells[4]?.innerText?.trim(),
                            '1B': cells[5]?.innerText?.trim(),
                            '2B': cells[6]?.innerText?.trim(),
                            '3B': cells[7]?.innerText?.trim(),
                            HR: cells[8]?.innerText?.trim(),
                            BB: cells[9]?.innerText?.trim(),
                            SO: cells[10]?.innerText?.trim(),
                            AVG: cells[11]?.innerText?.trim(),
                            OBP: cells[12]?.innerText?.trim(),
                            SLG: cells[13]?.innerText?.trim()
                        }
                    };
                }).filter(row => row !== null);
            }
        """)
        await browser.close()
        return rows_data

def get_streak_data():
    """Retrieve cached streak data from MongoDB for today's scrape date."""
    today_str = date.today().strftime("%Y-%m-%d")
    entry = streak_collection.find_one({"scrape_date": today_str}, {"_id": 0})  # Explicitly exclude _id
    return entry if entry else None



# Set to 1 for forced re-scraping (debug), 0 for normal behavior.
ALWAYS_SCRAPE = 1

async def scrape_streak_data():
    """Scrape streak data only if no cached entry exists for today's scrape date."""
    today_str = date.today().strftime("%Y-%m-%d")
    
    # Remove any cached data not from today.
    streak_collection.delete_many({"scrape_date": {"$ne": today_str}})
    
    if not ALWAYS_SCRAPE:
        cached_data = streak_collection.find_one({"scrape_date": today_str}, {"_id": 0})
        if cached_data:
            print(f"[DEBUG] Using cached streak data for {today_str}")
            return cached_data

    url = "https://www.baseballmusings.com/cgi-bin/CurStreak.py"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, timeout=15000, wait_until="domcontentloaded")
        
        date_element = await page.query_selector("h2")
        streak_date_scraped = await date_element.inner_text() if date_element else "Unknown"
        
        rows_data = await page.eval_on_selector_all("table tbody tr", r"""
rows => {
    const data = [];
    for (let row of rows) {
        let cells = row.querySelectorAll("td");
        const count = cells.length;
        if (count === 1) {
            let raw = cells[0].innerText.trim();
            if (raw.indexOf("\t") >= 0) {
                let parts = raw.split("\t").map(s => s.trim());
                if (parts.length >= 13) {
                    if (parts[0].toLowerCase().includes("player")) continue;
                    data.push({
                        player: parts[0],
                        games: parts[1],
                        atBats: parts[2],
                        runs: parts[3],
                        hits: parts[4],
                        hr: parts[5],
                        rbi: parts[6],
                        bb: parts[7],
                        k: parts[8],
                        ba: parts[9],
                        oba: parts[10],
                        slug: parts[11],
                        lastGameDate: parts[12]
                    });
                }
            }
        } else if (count === 13) {
            if (cells[0].innerText.toLowerCase().includes("player")) continue;
            data.push({
                player: cells[0].innerText.trim(),
                games: cells[1].innerText.trim(),
                atBats: cells[2].innerText.trim(),
                runs: cells[3].innerText.trim(),
                hits: cells[4].innerText.trim(),
                hr: cells[5].innerText.trim(),
                rbi: cells[6].innerText.trim(),
                bb: cells[7].innerText.trim(),
                k: cells[8].innerText.trim(),
                ba: cells[9].innerText.trim(),
                oba: cells[10].innerText.trim(),
                slug: cells[11].innerText.trim(),
                lastGameDate: cells[12].innerText.trim()
            });
        } else {
            continue;
        }
    }
    return data;
}
""")
        await browser.close()

        new_data = {
            "date": streak_date_scraped,
            "scrape_date": today_str,
            "players": rows_data
        }
        streak_collection.delete_many({"scrape_date": today_str})
        streak_collection.insert_one(new_data)
        print(f"[DEBUG] Cached new streak data for {today_str}")
        print(f"[DEBUG] Streak data extracted: {rows_data}")
        print(f"[DEBUG] Players on hot streak: {[player['player'] for player in rows_data if 'player' in player]}")
        return new_data

def store_data(date, data):
    """Deletes old data for the date if outdated, then stores fresh scraped data."""
    current_time = datetime.datetime.utcnow()

    # Add timestamp field to all entries
    cleaned_data = [{k: v for k, v in entry.items() if k != "_id"} for entry in data]
    for entry in cleaned_data:
        entry["date"] = date
        entry["last_updated"] = current_time

    collection.delete_many({"date": date})  # Clear outdated data
    collection.insert_many(cleaned_data)
    print(f"[DEBUG] Stored updated data for {date} at {current_time}")

def get_data(date):
    return list(collection.find({"date": date}, {"_id": 0}))

def get_current_est_date():
    """
    Return the current date in Eastern Time as a string in format YYYY-MM-DD.
    (No after-8PM adjustment is applied here.)
    """
    user_timezone = pytz.timezone("America/New_York")
    now_local = datetime.datetime.now(user_timezone)
    return now_local.date().strftime("%Y-%m-%d")

# ------------------------------
# ROUTE DEFINITIONS
# ------------------------------

@app.route("/")
def home():
    """
    Render the home page.
    If a query parameter 'date' is provided, use that;
    otherwise, use the current EST date.
    """
    query_date = request.args.get("date")
    date = query_date if query_date else get_current_est_date()
    print(f"[DEBUG] FINAL Date Used for Display: {date}")
    # Pass the date to the template so the client-side nav links can be built from it.
    return render_template("MyBatterVsPitcher.html", date=date)

@app.route("/stats")
def stats():
    query_date = request.args.get("date") or get_current_est_date()
    print(f"[DEBUG] Fetching stats for {query_date}")

    # Check if data exists and when it was last updated
    existing_entry = collection.find_one({"date": query_date}, {"_id": 0})
    
    if existing_entry:
        last_updated = existing_entry.get("last_updated")
        if last_updated:
            time_elapsed = datetime.datetime.utcnow() - last_updated

            # If data is less than 2 hours old, return cached data
            if time_elapsed.total_seconds() < 7200:
                print(f"[DEBUG] Using cached data for {query_date}, last updated {last_updated}")
                return jsonify(list(collection.find({"date": query_date}, {"_id": 0})))

    # Otherwise, scrape fresh data
    print(f"[DEBUG] Data for {query_date} is outdated, refreshing now.")
    scraped_data = asyncio.run(scrape_data(query_date))

    if scraped_data:
        store_data(query_date, scraped_data)
        return jsonify(scraped_data)

    return jsonify({"error": "No data found for this date"}), 404


from bson import ObjectId

def convert_object_ids(obj):
    if isinstance(obj, dict):
        return {k: convert_object_ids(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_object_ids(i) for i in obj]
    elif isinstance(obj, ObjectId):
        return str(obj)  # Convert ObjectId to string
    else:
        return obj

@app.route("/streak-data")
def streak_data():
    data = get_streak_data()
    if data is None:
        # If no cache is available for today, force a scrape.
        data = asyncio.run(scrape_streak_data())
    
    cleaned_data = convert_object_ids(data)  # Convert ObjectIds before returning
    return jsonify(cleaned_data)

#@app.route("/streak-data")
#def streak_data():
#    data = get_streak_data()
#    if data is None:
        # If no cache is available for today, force a scrape.
#        data = asyncio.run(scrape_streak_data())
#    return jsonify(data)


@app.route("/change-date")
def change_date():
    """
    Handle a date selection request.
    If data for the chosen date is not cached, scrape it.
    Then redirect to the home page with the chosen date.
    """
    query_date = request.args.get("date")
    date = query_date if query_date else get_current_est_date()
    print(f"[DEBUG] FINAL Date Before Redirect: {date}")
    cached_data = get_data(date)
    if not cached_data:
        scraped_data = asyncio.run(scrape_data(date))
        if scraped_data:
            store_data(date, scraped_data)
    return redirect(url_for("home", date=date))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)
