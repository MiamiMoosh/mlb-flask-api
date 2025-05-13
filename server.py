from flask import Flask, jsonify
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

def scrape_data():
    url = "https://swishanalytics.com/optimus/mlb/batter-vs-pitcher-stats?date=2025-05-14"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.find("table")
    print(soup.prettify())  # See the full page source
    data = []

    if table:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if cells:
                batter = cells[0].text.strip()
                pitcher = cells[1].text.strip()
                stats = cells[2].text.strip()
                data.append({"batter": batter, "pitcher": pitcher, "stats": stats})

    return data

@app.route("/stats")
def stats():
    return jsonify(scrape_data())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
