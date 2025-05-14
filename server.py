from flask import Flask, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import os

app = Flask(__name__)

def scrape_data():
    url = "https://swishanalytics.com/optimus/mlb/batter-vs-pitcher-stats?date=2025-05-14"

    # Set up Selenium WebDriver
    options = webdriver.ChromeOptions()
    options.binary_location = "/usr/bin/chromium"  # Use Chromium instead of Google Chrome

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

@app.route("/stats")
def stats():
    return jsonify(scrape_data())

@app.route("/debug")
def debug():
    import subprocess

    os_version = subprocess.run(["cat", "/etc/os-release"], capture_output=True, text=True).stdout.strip()
    
    # Check package managers
    apt_exists = subprocess.run(["which", "apt"], capture_output=True, text=True).stdout.strip()
    yum_exists = subprocess.run(["which", "yum"], capture_output=True, text=True).stdout.strip()
    apk_exists = subprocess.run(["which", "apk"], capture_output=True, text=True).stdout.strip()

    # Check Chrome installation
    chrome_path_google = subprocess.run(["which", "google-chrome"], capture_output=True, text=True).stdout.strip()
    chrome_path_chromium = subprocess.run(["which", "chromium"], capture_output=True, text=True).stdout.strip()

    chrome_version_google = subprocess.run(["google-chrome", "--version"], capture_output=True, text=True).stdout.strip()
    chrome_version_chromium = subprocess.run(["chromium", "--version"], capture_output=True, text=True).stdout.strip()

    return jsonify({
        "os_version": os_version,
        "package_managers": {
            "apt": apt_exists,
            "yum": yum_exists,
            "apk": apk_exists
        },
        "google_chrome_path": chrome_path_google,
        "chromium_path": chrome_path_chromium,
        "google_chrome_version": chrome_version_google,
        "chromium_version": chrome_version_chromium
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
