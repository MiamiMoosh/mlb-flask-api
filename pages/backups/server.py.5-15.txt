import os
import time
import asyncio
import datetime
from flask import Flask, jsonify, render_template, request
from playwright.async_api import async_playwright

# Initialize Flask app, updating template folder
app = Flask(__name__, template_folder="pages")  

port = int(os.environ.get("PORT", 8080))

# Dictionary for correct team abbreviations
team_abbreviations = {
    "whitesox": "CWS", "guardians": "CLE", "tigers": "DET", "royals": "KC", "twins": "MIN",
    "orioles": "BAL", "redsox": "BOS", "yankees": "NYY", "rays": "TB", "bluejays": "TOR",
    "athletics": "OAK", "astros": "HOU", "angels": "LAA", "mariners": "SEA", "rangers": "TEX",
    "cubs": "CHC", "reds": "CIN", "brewers": "MIL", "pirates": "PIT", "cardinals": "STL",
    "braves": "ATL", "marlins": "MIA", "mets": "NYM", "phillies": "PHI", "nationals": "WAS",
    "diamondbacks": "ARI", "rockies": "COL", "dodgers": "LAD", "padres": "SD", "giants": "SF"
}

async def scrape_data(date):
    url = f"https://swishanalytics.com/optimus/mlb/batter-vs-pitcher-stats?date={date}"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, timeout=15000, wait_until="domcontentloaded")

        print(f"[DEBUG] Scraping data for {date} from {url}")

        # Explicitly wait for the table before extracting rows
        try:
            await page.wait_for_selector("table tbody tr", timeout=10000)
        except Exception:
            print("[ERROR] Table not found or took too long to load!")
            return []

        # Extract table data with correct abbreviations
        rows_data = await page.eval_on_selector_all("table tbody tr", """
            rows => {
                console.log("[DEBUG] Extracting Rows...");
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

                    // ✅ Cleanup function to remove unwanted "$N/A" values and trim spaces
                    const removeNA = (text) => text.replace(/\$?N\/A/g, "").trim();

                    batterHandedness = removeNA(batterHandedness) ? `(${removeNA(batterHandedness)})` : "";
                    batterPosition = removeNA(batterPosition);
                    pitcherHandedness = removeNA(pitcherHandedness) ? `(${removeNA(pitcherHandedness)})` : "";

                    // ✅ Remove double parentheses only from handedness fields
                    const fixParentheses = (text) => text.replace(/[()]+/g, "").trim();

                    batterHandedness = batterHandedness ? `(${fixParentheses(batterHandedness)})` : "";
                    pitcherHandedness = pitcherHandedness ? `(${fixParentheses(pitcherHandedness)})` : "";


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

        print("[DEBUG] Final Extracted Data:", rows_data)
        await browser.close()

    return rows_data

@app.route("/")
def home():
    date = request.args.get("date", datetime.date.today().strftime("%Y-%m-%d"))
    return render_template("MyBatterVsPitcher.html", date=date)

@app.route("/stats")
def stats():
    date = request.args.get("date", datetime.date.today().strftime("%Y-%m-%d"))
    print(f"[DEBUG] Fetching stats for {date}...")

    data = asyncio.run(scrape_data(date))
    print("[DEBUG] Flask Returned Data:", data)

    return jsonify(data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)
