import os
import time
import asyncio
from flask import Flask, jsonify
from playwright.async_api import async_playwright

app = Flask(__name__)

# Ensure Railway uses the correct port
port = int(os.environ.get("PORT", 8080))

# Automatically install Playwright's browsers on startup
os.system("playwright install chromium")

async def scrape_data():
    url = "https://swishanalytics.com/optimus/mlb/batter-vs-pitcher-stats?date=2025-05-14"
    start_time = time.time()  # Start timing
    
    async with async_playwright() as p:
        print(f"[DEBUG] Starting Playwright at {time.strftime('%H:%M:%S')}")
        browser = await p.chromium.launch(headless=True, args=[
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-background-networking",
            "--disable-gpu",
            "--single-process",
            "--disable-software-rasterizer"
        ])
        print(f"[DEBUG] Browser launched in {time.time() - start_time:.2f} seconds")

        page = await browser.new_page()
        await page.set_extra_http_headers({"ngrok-skip-browser-warning": "true"})

        print(f"[DEBUG] Navigating to {url}...")
        nav_start = time.time()
        try:
            await page.goto(url, timeout=5000)
        except Exception:
            print(f"[ERROR] Page load timeout at {time.strftime('%H:%M:%S')}, retrying...")
            await page.goto(url, timeout=2000, wait_until="domcontentloaded")
        print(f"[DEBUG] Page loaded in {time.time() - nav_start:.2f} seconds")

        wait_start = time.time()
        await page.wait_for_selector("table tbody tr", timeout=5000)
        print(f"[DEBUG] Table appeared in {time.time() - wait_start:.2f} seconds")

        extract_start = time.time()

        # Extract all rows' data in **one single operation**
        rows_data = await page.eval_on_selector_all("table tbody tr", """
            rows => rows.map(row => {
                let cells = row.querySelectorAll("td");
                if (cells.length < 14) return null;
                return {
                    batter: cells[0].innerText.trim(),
                    team: cells[1].innerText.trim(),  // Double-check this index
                    pitcher: cells[2].innerText.trim(),
                    stats: {
                        PA: cells[3].innerText.trim(),
                        AB: cells[4].innerText.trim(),
                        H: cells[5].innerText.trim(),
                        '1B': cells[6].innerText.trim(),
                        '2B': cells[7].innerText.trim(),
                        '3B': cells[8].innerText.trim(),
                        HR: cells[9].innerText.trim(),
                        BB: cells[10].innerText.trim(),
                        SO: cells[11].innerText.trim(),
                        AVG: cells[12].innerText.trim(),
                        OBP: cells[13].innerText.trim(),
                        SLG: cells[14].innerText.trim()
                    }
                };
            }).filter(row => row !== null)
        """)


        print(f"[DEBUG] Batch data extraction completed in {time.time() - extract_start:.2f} seconds")

        await browser.close()
        print(f"[DEBUG] Browser closed at {time.strftime('%H:%M:%S')}")

    return rows_data

@app.route("/")
def home():
    return jsonify({"message": "Welcome to the MLB Stats API!"})

@app.route("/stats")
def stats():
    return jsonify(asyncio.run(scrape_data()))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)  # Ensures Railway exposes the app publicly
