from flask import Flask, jsonify
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

app = Flask(__name__)

def scrape_data():
    url = "https://swishanalytics.com/optimus/mlb/batter-vs-pitcher-stats?date=2025-05-14"

    # Set up Selenium WebDriver
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Runs Chrome in the background (no GUI)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # Load the page
    driver.get(url)
    time.sleep(5)  # Give JavaScript time to load the stats table

    # Find the table element
    table = driver.find_element(By.TAG_NAME, "table")
    rows = table.find_elements(By.TAG_NAME, "tr")

    data = []

    for row in rows:
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) >= 3:
            batter = cells[0].text.strip()
            pitcher = cells[1].text.strip()
            stats = cells[2].text.strip()
            data.append({"batter": batter, "pitcher": pitcher, "stats": stats})

    driver.quit()
    return data

@app.route("/stats")
def stats():
    return jsonify(scrape_data())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
