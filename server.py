from flask import Flask, jsonify
from playwright.sync_api import sync_playwright

app = Flask(__name__)

def scrape_data():
    url = "https://swishanalytics.com/optimus/mlb/batter-vs-pitcher-stats?date=2025-05-14"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  # Uses Playwright's managed Chromium
        page = browser.new_page()
        page.goto(url)
        page.wait_for_selector("table tbody tr")

        rows = page.query_selector_all("table tbody tr")

        data = []
        for row in rows:
            cells = row.query_selector_all("td")
            if len(cells) >= 14:
                batter = cells[0].inner_text().strip()
                pitcher = cells[1].inner_text().strip()

                stats = {
                    "PA": cells[2].inner_text().strip(),
                    "AB": cells[3].inner_text().strip(),
                    "H": cells[4].inner_text().strip(),
                    "1B": cells[5].inner_text().strip(),
                    "2B": cells[6].inner_text().strip(),
                    "3B": cells[7].inner_text().strip(),
                    "HR": cells[8].inner_text().strip(),
                    "BB": cells[9].inner_text().strip(),
                    "SO": cells[10].inner_text().strip(),
                    "AVG": cells[11].inner_text().strip(),
                    "OBP": cells[12].inner_text().strip(),
                    "SLG": cells[13].inner_text().strip()
                }

                data.append({
                    "batter": batter,
                    "pitcher": pitcher,
                    "stats": stats
                })

        browser.close()
    return data

@app.route("/stats")
def stats():
    return jsonify(scrape_data())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
