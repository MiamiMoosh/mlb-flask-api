import os
import time
import asyncio
import datetime
import pytz
from flask import Flask, jsonify, render_template, request, redirect, url_for
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

def store_data(date, data):
    """Store scraped data in MongoDB; add a 'date' field to each record."""
    cleaned_data = [{k: v for k, v in entry.items() if k != "_id"} for entry in data]
    for entry in cleaned_data:
        entry["date"] = date
    collection.delete_many({"date": date})
    collection.insert_many(cleaned_data)
    print(f"[DEBUG] Stored cleaned data for {date}: {cleaned_data}")

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
    """
    Fetch MLB stats for the given date.
    If no query parameter is provided, use the current EST date.
    """
    query_date = request.args.get("date")
    date = query_date if query_date else get_current_est_date()
    print(f"[DEBUG] FINAL Corrected Date Sent for Scraping: {date}")
    cached_data = get_data(date)
    if cached_data:
        return jsonify(cached_data)
    scraped_data = asyncio.run(scrape_data(date))
    if scraped_data:
        store_data(date, scraped_data)
        return jsonify(scraped_data)
    return jsonify({"error": "No data found for this date"}), 404

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
