from flask import Flask, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import os
import subprocess

app = Flask(__name__)

def scrape_data():
    url = "https://swishanalytics.com/optimus/mlb/batter-vs-pitcher-stats?date=2025-05-14"

    # Use remote WebDriver instead of local Chrome/Chromium
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    try:
        driver = webdriver.Remote(
            command_executor="http://hub.browserstack.com/wd/hub",
            options=options
        )

        driver.get(url)

        # Explicit wait for table rows to ensure data loads
        wait = WebDriverWait(driver, 15)
        rows = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//table/tbody/tr")))

        data = []
        for row in rows:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) >= 14:  # Ensure enough columns exist
                batter = cells[0].text.strip()
                pitcher = cells[1].text.strip()

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
                    "pitcher": pitcher,
                    "stats": stats
                })

    except Exception as e:
        data = {"error": f"Failed to scrape data: {str(e)}"}

    driver.quit()
    return data

@app.route("/stats")
def stats():
    return jsonify(scrape_data())

@app.route("/debug")
def debug():
    # Gather system information to debug missing browser issues
    os_version = subprocess.run(["cat", "/etc/os-release"], capture_output=True, text=True).stdout.strip()
    
    package_managers = {
        "apt": subprocess.run(["which", "apt"], capture_output=True, text=True).stdout.strip(),
        "yum": subprocess.run(["which", "yum"], capture_output=True, text=True).stdout.strip(),
        "apk": subprocess.run(["which", "apk"], capture_output=True, text=True).stdout.strip(),
    }

    chrome_path_google = subprocess.run(["which", "google-chrome"], capture_output=True, text=True).stdout.strip()
    chrome_path_chromium = subprocess.run(["which", "chromium"], capture_output=True, text=True).stdout.strip()

    chrome_version_google = subprocess.run(["google-chrome", "--version"], capture_output=True, text=True).stdout.strip()
    chrome_version_chromium = subprocess.run(["chromium", "--version"], capture_output=True, text=True).stdout.strip()

    return jsonify({
        "os_version": os_version,
        "package_managers": package_managers,
        "google_chrome_path": chrome_path_google,
        "chromium_path": chrome_path_chromium,
        "google_chrome_version": chrome_version_google,
        "chromium_version": chrome_version_chromium
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
