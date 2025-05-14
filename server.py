from flask import Flask, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

app = Flask(__name__)

def scrape_data():
    url = "https://swishanalytics.com/optimus/mlb/batter-vs-pitcher-stats?date=2025-05-14"

    import os

    options = webdriver.ChromeOptions()

    # Check for available Chrome binaries and set one
    binary_paths = ["/usr/bin/chromium", "/usr/bin/google-chrome"]
    for path in binary_paths:
        if os.path.exists(path):
            options.binary_location = path
            break

    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    driver.get(url)

    try:
        # Explicit wait for table rows to ensure data loads
        wait = WebDriverWait(driver, 15)
        rows = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//table/tbody/tr")))

        data = []
        for row in rows:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) >= 14:  # Ensure enough columns exist
                
                # Extract team icons
                batter_img = cells[0].find_element(By.TAG_NAME, "img")
                pitcher_img = cells[1].find_element(By.TAG_NAME, "img")

                batter_team = batter_img.get_attribute("alt")  # Extract team name
                pitcher_team = pitcher_img.get_attribute("alt")

                # If alt is empty, extract team name from filename in src URL
                if not batter_team:
                    batter_team = batter_img.get_attribute("src").split("/")[-1].split(".")[0]
                if not pitcher_team:
                    pitcher_team = pitcher_img.get_attribute("src").split("/")[-1].split(".")[0]

                batter = cells[0].text.strip()
                pitcher = cells[1].text.strip()
                
                # Expanded stats
                stats = {
                    "PA": cells[2].text.strip(),
                    "AB": cells[3].text.strip(),
                    "H": cells[4].text.strip(),
                    "1B": cells[5].text.strip(),
                    "2B": cells[6].text.strip(),
                    "3B": cells[7].text.strip(),
                    "HR": cells[8].text.strip(),
                    "BB": cells[9].text.strip(),
                    "SO": cells[10].text.strip(),
                    "AVG": cells[11].text.strip(),
                    "OBP": cells[12].text.strip(),
                    "SLG": cells[13].text.strip()
                }
                
                data.append({
                    "batter": batter,
                    "batter_team": batter_team,
                    "pitcher": pitcher,
                    "pitcher_team": pitcher_team,
                    "stats": stats
                })

    except Exception as e:
        data = {"error": f"Failed to scrape data: {str(e)}"}

    driver.quit()
    return data

@app.route("/debug")
def debug():
    import subprocess
    chrome_path = subprocess.run(["which", "chromium-browser"], capture_output=True, text=True).stdout.strip()
    chrome_version = subprocess.run(["chromium-browser", "--version"], capture_output=True, text=True).stdout.strip()
    return jsonify({"chromium_path": chrome_path, "chromium_version": chrome_version})

@app.route("/stats")
def stats():
    return jsonify(scrape_data())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
