import os
import asyncio
import datetime
import pytz
import subprocess
import requests
import slugify
import json
import re
import threading
import subprocess


from flask import Flask, jsonify, render_template,  request, redirect, url_for, session, flash
from bson import ObjectId
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import date, datetime, timedelta, timezone
from playwright.async_api import async_playwright
from pymongo import MongoClient
from itsdangerous import URLSafeTimedSerializer
from flask_mail import Mail, Message
from functools import wraps
from flask_cors import CORS
from insight_utils import generate_or_fetch_matchup_insight, generate_matchup_insight, get_recent_batter_insight, \
    get_pitcher_mix, extract_matchup_pair
from game_logic import extract_game_state, is_high_leverage
from sportsdb_api import get_games_for_league, get_leagues

# Initialize Flask app
app = Flask(__name__, template_folder="pages")
app.secret_key = "The5Weapon!33534"  # Replace this with a strong, unique string in production
serializer = URLSafeTimedSerializer(app.secret_key)
port = int(os.environ.get("PORT", 8080))
CORS(app)

PRINTIFY_API_TOKEN = os.environ.get("PRINTIFY_API_TOKEN")
HEADERS = {"Authorization": f"Bearer {PRINTIFY_API_TOKEN}"}
SHOP_ID = os.environ.get("PRINTIFY_SHOP_ID")

response = requests.get("https://api.printify.com/v1/shops.json", headers=HEADERS)
print(response.json())

# Connect to MongoDB using Railway-provided URI
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo:MXQDxgcJWYBgTFtLPiwGdsnRXTIONzNc@trolley.proxy.rlwy.net:25766")
client = MongoClient(MONGO_URI)

# MLB stats DB
mlb_db = client["mlb_stats"]
collection = mlb_db["batter_vs_pitcher"]
streak_collection = mlb_db["hot_streak_players"]

# First String users DB
users_db = client["first_string_users"]
users_collection = users_db["users"]
listings_collection = users_db["listings"]
page_views = users_db["page_views"]
search_logs = users_db["search_logs"]
bot_views = users_db["bot_views"]
banned_emails = users_db["banned_emails"]

# Threadline DB
threadline_db = client["threadline"]
threadline_comments = threadline_db["threadline_comments"]
threadline_users = threadline_db["threadline_users"]
threadline_insights = threadline_db["threadline_insights"]
threadline_games = threadline_db["threadline_games"]
threadline_surveys = threadline_db["threadline_surveys"]
threadline_votes = threadline_db["threadline_votes"]
user_reputation = threadline_db["user_reputation"]

MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
app.config.update(
    MAIL_SERVER="smtp.gmail.com",
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME="firststring.biz@gmail.com",
    MAIL_PASSWORD=MAIL_PASSWORD,
    MAIL_DEFAULT_SENDER="First String <noreply@firststring.com>"
)

mail = Mail(app)


def run_sync_script():
    try:
        subprocess.run(["python", "sync_printify.py"], check=True)
    except Exception as e:
        print(f"⚠️ Sync script failed: {e}")

threading.Thread(target=run_sync_script).start()


def extract_tags(text):
    tags = []
    lowered = text.lower()
    if any(word in lowered for word in ["momentum", "swing", "shift", "flip"]):
        tags.append("momentum")
    if any(word in lowered for word in ["collapse", "choke", "fall apart"]):
        tags.append("collapse")
    if any(word in lowered for word in ["clutch", "ice cold", "step up"]):
        tags.append("clutch")
    if any(word in lowered for word in ["blow", "lead gone", "meltdown"]):
        tags.append("meltdown")
    return tags


def detect_players(text, player_names):
    found = []
    for name in player_names:
        if name.lower() in text.lower():
            found.append(name)
    return list(set(found))  # remove duplicates


def track(slug):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            track_view(slug)
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def is_bot(user_agent):
    bot_signatures = [
        "bot", "spider", "crawl", "slurp", "fetch", "monitor", "pingdom",
        "headless", "python-requests", "httpclient", "wget", "curl"
    ]
    ua = user_agent.lower()
    return any(sig in ua for sig in bot_signatures)


def track_view(slug):
    ua = request.headers.get("User-Agent", "")
    if is_bot(ua):
        bot_views.insert_one({
            "slug": slug,
            "user_agent": ua,
            "referrer": request.referrer,
            "ip": request.remote_addr,
            "timestamp": datetime.now(timezone.utc)
        })
        return

    ref = request.referrer or "direct"
    ip = request.remote_addr

    page_views.update_one(
        {"slug": slug},
        {
            "$inc": {"hits": 1},
            "$set": {"last_viewed": datetime.now(timezone.utc)},
            "$push": {
                "sources": {
                    "referrer": ref,
                    "user_agent": ua,
                    "ip": ip,
                    "timestamp": datetime.now(timezone.utc)
                }
            }
        },
        upsert=True
    )


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("role") != "admin":
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html")


@app.route("/cms/users")
def manage_users():
    if session.get("role") != "admin":
        return redirect(url_for("login"))

    users = list(users_collection.find({}, {"_id": 0, "password_hash": 0}))
    return render_template("manage_users.html", users=users)


@app.route("/cms/create_user", methods=["POST"])
def create_user():
    if session.get("role") != "admin":
        return redirect(url_for("login"))

    username = request.form["username"]
    password = request.form["password"]
    role = request.form["role"]
    plan = request.form["plan"]

    if users_collection.find_one({"username": username}):
        return "Username already exists", 400

    users_collection.insert_one({
        "username": username,
        "password_hash": generate_password_hash(password),
        "role": role,
        "plan": plan
    })

    return redirect(url_for("admin_manage_users"))


@app.route("/webhook/etsy", methods=["POST"])
def etsy_webhook():
    data = request.json  # Get webhook data
    listing_id = data.get("listing_id")

    if listing_id:
        save_listing_to_db(listing_id, custom_keywords=[])  # Auto-import listing
        return jsonify({"status": "success"})

    return jsonify({"status": "error", "message": "Invalid data"}), 400


@app.route("/admin/listings")
@admin_required
def admin_listings():
    listings = listings_collection.find()
    return render_template("listings.html", listings=listings)


@app.route("/admin/manage-users")
@admin_required
def admin_manage_users():
    query = request.args.get("q")
    if query:
        users = users_collection.find({
            "$or": [
                {"username": {"$regex": query, "$options": "i"}},
                {"email": {"$regex": query, "$options": "i"}}
            ]
        })
    else:
        users = users_collection.find()
    return render_template("manage_users.html", users=users)


@app.route("/admin/user/<username>")
@admin_required
def admin_view_user(username):
    user = users_collection.find_one({"username": username}, {"_id": 0, "password_hash": 0})
    if not user:
        return "User not found", 404
    return render_template("user_detail.html", user=user)


@app.route("/admin/reset-password", methods=["POST"])
@admin_required
def admin_reset_password():
    username = request.form.get("username")
    new_pw = request.form.get("new_password")

    if not username or not new_pw:
        flash("Username or new password missing. Please try again.", "danger")
        return redirect(url_for("admin_manage_users"))

    hashed_pw = generate_password_hash(new_pw)
    result = users_collection.update_one(
        {"username": username},
        {"$set": {"password_hash": hashed_pw}}
    )

    if result.modified_count == 1:
        flash(f"Password successfully reset for {username}.", "success")
    else:
        flash(f"Could not reset password for {username}.", "warning")

    return redirect(url_for("admin_view_user", username=username))


@app.route("/admin/ban-email", methods=["POST"])
@admin_required
def ban_email():
    email = request.form["email"]
    banned_emails.insert_one({"email": email})
    flash(f"Email address {email} has been banned.", "warning")
    return redirect(url_for("admin_manage_users"))


@app.route("/admin/search-analytics")
@admin_required
def search_analytics():
    top_queries = search_logs.aggregate([
        {"$group": {"_id": "$query", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 50}
    ])
    return render_template("search_analytics.html", queries=top_queries)


@app.route("/admin/page-traffic")
@admin_required
def page_traffic():
    sort_field = request.args.get("sort", "hits")
    include_bots = request.args.get("bots", "off") == "on"

    pages = list(page_views.find().sort(sort_field, -1))

    for page in pages:
        sources = page.get("sources", [])
        if not include_bots:
            sources = [s for s in sources if not is_bot(s.get("user_agent", ""))]

        ref_counts = {}
        for s in sources:
            ref = s.get("referrer", "direct")
            ref_counts[ref] = ref_counts.get(ref, 0) + 1
        page["ref_summary"] = sorted(ref_counts.items(), key=lambda x: -x[1])[:3]

    return render_template("traffic_report.html", pages=pages, include_bots=include_bots)


@app.route("/admin/listings/new", methods=["GET", "POST"])
@admin_required
def new_listing():
    if request.method == "POST":
        title = request.form["title"]
        category = request.form["category"]
        price = float(request.form["price"])
        description = request.form["description"]

        listings_collection.insert_one({
            "title": title,
            "category": category,
            "price": price,
            "description": description,
            "created_at": datetime.now(timezone.utc)
        })

        return redirect(url_for("admin_listings"))

    return render_template("listings_form.html", listing=None)


@app.route("/admin/listings/<id>/edit", methods=["GET", "POST"])
@admin_required
def edit_listing(listing_id):
    listing = listings_collection.find_one({"_id": ObjectId(listing_id)})

    if request.method == "POST":
        listings_collection.update_one({"_id": ObjectId(listing_id)}, {
            "$set": {
                "title": request.form["title"],
                "category": request.form["category"],
                "price": float(request.form["price"]),
                "description": request.form["description"]
            }
        })
        return redirect(url_for("admin_listings"))

    return render_template("listings_form.html", listing=listing)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"]
        user = users_collection.find_one({"email": email})
        if not user:
            return "Email not found", 404

        token = serializer.dumps(email, salt="password-reset")
        reset_url = url_for("reset_password", token=token, _external=True)

        # Load HTML email template (inline or from file)
        html_body = render_template("emails/password_reset.html", reset_url=reset_url, year=datetime.now().year)

        msg = Message("Reset Your First String Password", recipients=[email], html=html_body)
        mail.send(msg)

        return "A reset link has been sent to your email."

    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        email = serializer.loads(token, salt="password-reset", max_age=3600)
    except Exception:
        return "Reset link is invalid or has expired", 403

    if request.method == "POST":
        new_pw = request.form["password"]
        hashed = generate_password_hash(new_pw)
        users_collection.update_one({"email": email}, {"$set": {"password_hash": hashed}})
        return redirect(url_for("login"))

    return render_template("reset_password.html", token=token)


@app.route("/cms/update_user", methods=["POST"])
def update_user():
    if session.get("role") != "admin":
        return redirect(url_for("login"))

    username = request.form["username"]
    plan = request.form["plan"]

    users_collection.update_one({"username": username}, {"$set": {"plan": plan}})
    return redirect(url_for("admin_manage_users"))


@app.route("/cms/delete_user", methods=["POST"])
def delete_user():
    if session.get("role") != "admin":
        return redirect(url_for("login"))

    username = request.form["username"]
    users_collection.delete_one({"username": username})
    return redirect(url_for("admin_manage_users"))


@app.route("/cms/update_role", methods=["POST"])
def update_role():
    if session.get("role") != "admin":
        return redirect(url_for("login"))

    username = request.form["username"]
    role = request.form["role"]

    users_collection.update_one({"username": username}, {"$set": {"role": role}})
    return redirect(url_for("admin_manage_users"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identity = request.form["username"]
        password = request.form["password"]

        user = users_collection.find_one({
            "$or": [{"username": identity}, {"email": identity}]
        })

        if user and check_password_hash(user["password_hash"], password):
            session["logged_in"] = True
            session["username"] = user["username"]
            session["role"] = user.get("role", "user")
            return redirect(url_for("admin_dashboard") if user.get("role") == "admin" else url_for("user_dashboard"))

        return "Invalid credentials", 401

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        plan = request.form.get("plan", "free")

        if users_collection.find_one({"$or": [{"username": username}, {"email": email}]}):
            return "Username or email already exists", 400

        users_collection.insert_one({
            "name": name,
            "username": username,
            "email": email,
            "password_hash": generate_password_hash(password),
            "role": "user",
            "plan": plan
        })

        session["logged_in"] = True
        session["username"] = username
        session["role"] = "user"
        track_view("/register")
        return redirect(url_for("user_dashboard"))

    return render_template("register.html")


@app.route("/cms")
def cms_dashboard():
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    return render_template("admin_dashboard.html")


@app.route("/dashboard")
def user_dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    user = users_collection.find_one({"username": session["username"]}, {"_id": 0, "password_hash": 0})
    if not user:
        return "User not found", 404
    track_view("/dashboard")
    return render_template("user_dashboard.html", user=user)


async def scrape_all_data(target_date):
    # Run both scrapers concurrently
    async with asyncio.TaskGroup() as tg:
        streak_task = tg.create_task(scrape_streak_data())
        stats_task = tg.create_task(scrape_data(target_date))

        streak_data1, stats_data = await asyncio.gather(streak_task, stats_task)

    return streak_data1, stats_data


async def scrape_data(target_date):
    url = f"https://swishanalytics.com/optimus/mlb/batter-vs-pitcher-stats?date={target_date}"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, timeout=15000, wait_until="domcontentloaded")

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
            # print(f"[DEBUG] Using cached streak data for {today_str}")
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
        return new_data


def store_data(target_date, data):
    """Deletes old data for the date if outdated, then stores fresh scraped data."""
    current_time = datetime.now(timezone.utc)

    # Add timestamp field to all entries
    cleaned_data = [{k: v for k, v in entry.items() if k != "_id"} for entry in data]
    for entry in cleaned_data:
        entry["date"] = target_date
        entry["last_updated"] = current_time

    collection.delete_many({"date": target_date})  # Clear outdated data
    collection.insert_many(cleaned_data)
    # print(f"[DEBUG] Stored updated data for {target_date} at {current_time}")


def get_data(target_date):
    return list(collection.find({"date": target_date}, {"_id": 0}))


def get_current_est_date():
    """
    Return the current date in Eastern Time as a string in format YYYY-MM-DD.
    (No after-8PM adjustment is applied here.)
    """
    user_timezone = pytz.timezone("America/New_York")
    now_local = datetime.now(user_timezone)
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
    target_date = query_date if query_date else get_current_est_date()
    # Pass the date to the template so the client-side nav links can be built from it.
    track_view("/")
    return render_template("MyBatterVsPitcher.html", date=target_date, nav=load_nav())


@app.route("/stats")
def stats():
    query_date = request.args.get("date") or get_current_est_date()
    # print(f"[DEBUG] Fetching stats for {query_date}")

    # Check if data exists and when it was last updated
    existing_entry = collection.find_one({"date": query_date}, {"_id": 0})

    if existing_entry:
        last_updated = existing_entry.get("last_updated")
        if last_updated.tzinfo is None:
            last_updated = last_updated.replace(tzinfo=timezone.utc)
        if last_updated:
            time_elapsed = datetime.now(timezone.utc) - last_updated

            # If data is less than 2 hours old, return cached data
            if time_elapsed.total_seconds() < 7200:
                # print(f"[DEBUG] Using cached data for {query_date}, last updated {last_updated}")
                return jsonify(list(collection.find({"date": query_date}, {"_id": 0})))

    # Otherwise, scrape fresh data
    # print(f"[DEBUG] Data for {query_date} is outdated, refreshing now.")
    scraped_data = asyncio.run(scrape_data(query_date))

    if scraped_data:
        store_data(query_date, scraped_data)
        return jsonify(scraped_data)

    return jsonify({"error": "No data found for this date"}), 404


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


@app.route("/change-date")
def change_date():
    """
    Handle a date selection request.
    If data for the chosen date is not cached, scrape it.
    Then redirect to the home page with the chosen date.
    """
    query_date = request.args.get("date")
    target_date = query_date if query_date else get_current_est_date()
    # print(f"[DEBUG] FINAL Date Before Redirect: {target_date}")
    cached_data = get_data(target_date)
    if not cached_data:
        scraped_data = asyncio.run(scrape_data(date))
        if scraped_data:
            store_data(date, scraped_data)
    return redirect(url_for("home", date=target_date))


@app.route("/stats/daily-bvp")
def daily_bvp():
    query_date = request.args.get("date")
    target_date = query_date if query_date else get_current_est_date()
    track_view("/stats/daily-bvp")
    return render_template("MyBatterVsPitcher.html", date=target_date)


@app.route("/index.html")
def index_redirect():
    return redirect(url_for("home"))


# @app.before_request
# def debug_request_info():
    # print(f"Request URL: {request.url}")
    # print(f"Request Scheme: {request.scheme}")
    # print(f"Headers: {dict(request.headers)}")

    # if request.endpoint and request.endpoint != "static":  # ✅ Prevents error for static files
    # print(f"Request endpoint: {request.endpoint}")


def enforce_https():
    if request.headers.get("X-Forwarded-Proto") != "https":
        return redirect(request.url.replace("http://", "https://"), code=301)


def redirect_www():
    if request.host.startswith("www."):
        return redirect(request.url.replace("www.", ""), code=301)


@app.route("/admin/terminal", methods=["GET", "POST"])
def admin_terminal():
    output = ""
    if request.method == "POST":
        command = request.form.get("command")
        if command:
            try:
                output = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT).decode()
            except subprocess.CalledProcessError as e:
                output = e.output.decode()
    return render_template("terminal.html", output=output)


@app.route("/threadline/upvote", methods=["POST"])
def upvote_comment():
    data = request.get_json()
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    threadline_users.update_one(
        {"user_id": user_id},
        {"$inc": {"cred_score": 2}}
    )
    return jsonify({"status": "ok"})


@app.route("/threadline/mute", methods=["POST"])
def mute_comment():
    data = request.get_json()
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    threadline_users.update_one(
        {"user_id": user_id},
        {"$inc": {"cred_score": -1}}
    )
    return jsonify({"status": "ok"})


@app.route("/threadline/comments/<game_id>")
def get_threadline_comments(game_id):
    comments = list(threadline_comments.find(
        {"game_id": game_id},
        {"_id": 0}
    ).sort("timestamp", 1))

    # Patch inconsistent fields
    for c in comments:
        if "username" not in c and "user_display" in c:
            c["username"] = c["user_display"]

    # print(f"→ Returning {len(comments)} comments for {game_id}")
    # for c in comments:
        # print(c)

    return jsonify(comments)


@app.route("/threadline/comment", methods=["POST"])
def post_comment():
    data = request.get_json()
    game_id = data.get("game_id")
    text = data.get("text", "").strip()
    sport = data.get("sport", "mlb")  # 🔥 default for now if not provided
    now = datetime.now(timezone.utc)

    if not game_id or not text:
        return jsonify({"error": "Missing game_id or text"}), 400

    if session.get("logged_in") and session.get("username"):
        user_display = session["username"]
        is_anon = False
    else:
        anon_name = session.get("anon_name")
        if not anon_name:
            anon_name = f"Anon-{os.urandom(2).hex()[:4]}"
            session["anon_name"] = anon_name
        user_display = anon_name
        is_anon = True

        threadline_users.update_one(
            {"user_id": anon_name},
            {
                "$setOnInsert": {"cred_score": 100, "badge": "Rookie"},
                "$set": {"last_active": now}
            },
            upsert=True
        )

    cached_player_list = []  # should be populated in future phases

    comment = {
        "game_id": game_id,
        "sport": sport,
        "username": user_display,
        "text": text,
        "is_anon": is_anon,
        "cred_at_post": 100 if is_anon else None,
        "timestamp": now,
        "tags": extract_tags(text),
        "player_mentions": detect_players(text, cached_player_list)
    }

    threadline_comments.insert_one(comment)
    return jsonify({"username": user_display, "text": text})


@app.route("/threadline/comments/<sport>/<game_id>")
def get_threadline_comments_by_sport(sport, game_id):
    # Fetch game metadata for validation/context
    game = threadline_games.find_one({"game_id": game_id})
    if not game:
        return jsonify({"error": "Game not found"}), 404

    # Optional: Redirect if URL sport doesn't match database sport
    if game.get("sport", "").lower() != sport.lower():
        correct_sport = game["sport"]
        return redirect(url_for("get_threadline_comments_by_sport", sport=correct_sport, game_id=game_id))

    # Fetch comments for this game, sorted by timestamp
    comments = list(threadline_comments.find(
        {"sport": sport, "game_id": game_id},
        {"_id": 0}
    ).sort("timestamp", 1))

    for c in comments:
        if "username" not in c and "user_display" in c:
            c["username"] = c["user_display"]
        if "timestamp" in c and isinstance(c["timestamp"], datetime):
            c["timestamp"] = c["timestamp"].isoformat()

    return jsonify({
        "game_id": game_id,
        "sport": game["sport"],
        "home_team": game["home_team"],
        "away_team": game["away_team"],
        "scheduled_time": game["scheduled_time"],
        "status": game.get("status", "Scheduled"),
        "comments": comments
    })


def update_badges():
    for user in threadline_users.find():
        cred = user.get("cred_score", 0)
        badge = "Rookie Threader"
        if cred < 50:
            badge = "Comment Dust"
        elif cred < 100:
            badge = "Rookie Threader"
        elif cred < 150:
            badge = "Thread Sharp"
        elif cred < 200:
            badge = "Signal Riser"
        else:
            badge = "Thread Prophet"

        threadline_users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"badge": badge}}
        )


@app.route("/threadline/feed", methods=["GET"])
def get_comment_feed():
    game_id = request.args.get("game_id")
    if not game_id:
        return jsonify({"error": "Missing game_id"}), 400

    comments = list(threadline_comments.find(
        {"game_id": game_id},
        {"_id": 0}
    ).sort("timestamp", 1))  # 1 = ascending

    return jsonify(comments)


@app.route("/threadline/insight")
def insight():
    batter = request.args.get("batter")
    pitcher = request.args.get("pitcher")
    game_id = request.args.get("game_id")

    existing = threadline_insights.find_one({
        "batter": batter,
        "pitcher": pitcher,
        "game_id": game_id
    })

    if existing:
        return jsonify(existing["insights"])

    # Generate fresh if not cached
    batter_blurb = get_recent_batter_insight(batter)
    pitcher_blurb = get_pitcher_mix(pitcher)

    threadline_insights.insert_one({
        "batter": batter,
        "pitcher": pitcher,
        "game_id": game_id,
        "insights": {
            "batter": batter_blurb,
            "pitcher": pitcher_blurb
        },
        "cached_at": datetime.now(timezone.utc)
    })

    return jsonify({
        "batter": batter_blurb,
        "pitcher": pitcher_blurb
    })


@app.route("/threadline/matchup-insight")
def matchup_insight():
    batter = request.args.get("batter")
    pitcher = request.args.get("pitcher")

    if not batter or not pitcher:
        return jsonify({"error": "Missing batter or pitcher name"}), 400

    result = generate_matchup_insight(batter, pitcher)
    return jsonify(result)


@app.route("/threadline/<game_id>", methods=["GET", "POST"])
def view_threadline(game_id):
    # Handle incoming comment
    if request.method == "POST":
        comment_text = request.form.get("text", "").strip()
        if comment_text:
            username = session.get("username") or session.get("anon_name")
            if not username:
                username = f"Anon-{os.urandom(2).hex()[:4]}"
                session["anon_name"] = username
            threadline_comments.insert_one({
                "game_id": game_id,
                "username": username,
                "text": comment_text,
                "timestamp": datetime.now(timezone.utc)
            })
        return redirect(url_for("view_threadline", game_id=game_id))

    # Load recent comments (chronological for chat flow)
    comments = list(threadline_comments.find(
        {"game_id": game_id},
        {"_id": 0}
    ).sort("timestamp", 1))  # ascending

    # Load insights
    insights = list(threadline_insights.find(
        {"game_id": game_id},
        {"_id": 0}
    ))

    # User identity
    if session.get("logged_in") and session.get("username"):
        user_display = session["username"]
        is_anon = False
    else:
        anon_name = session.get("anon_name")
        if not anon_name:
            anon_name = f"Anon-{os.urandom(2).hex()[:4]}"
            session["anon_name"] = anon_name
        user_display = anon_name
        is_anon = True

    # Load matchup info
    game = threadline_games.find_one({"game_id": game_id})
    if not game:
        return f"Game not found: {game_id}", 404

    home_team = game.get("home_team", "")
    away_team = game.get("away_team", "")
    scheduled_time = game.get("scheduled_time", "TBD")
    status = game.get("status", "Scheduled")
    sport = game.get("sport", "")

    # Sport icon map
    sport_icons = {
        "baseball": "⚾", "basketball": "🏀", "football": "🏈",
        "hockey": "🏒", "soccer": "⚽"
    }
    sport_icon = sport_icons.get(sport.lower(), "🎮")

    # Extract matchup insights
    batter, pitcher = extract_matchup_pair(game_id, game)
    matchup_insight1 = None
    if batter and pitcher:
        matchup_insight1 = generate_or_fetch_matchup_insight(game_id, batter, pitcher, threadline_insights)

    # Current game state
    game_state = extract_game_state(game)

    # Check for triggerable high-leverage survey (priority)
    if is_high_leverage(game_state):
        survey = threadline_surveys.find_one({
            "game_id": game_id,
            "trigger_event": "high_leverage"
        })
    else:
        # Otherwise show latest
        survey = threadline_surveys.find_one(
            {"game_id": game_id},
            sort=[("timestamp", -1)]
        )

    user_vote = None
    result_counts = {}
    percentages = {}

    if survey:
        vote_doc = threadline_votes.find_one({
            "survey_id": survey["_id"],
            "username": user_display
        })
        user_vote = vote_doc.get("selected_option") if vote_doc else None

        if user_vote:
            all_votes = list(threadline_votes.find({"survey_id": survey["_id"]}))
            total = len(all_votes)
            for v in all_votes:
                opt = v["selected_option"]
                result_counts[opt] = result_counts.get(opt, 0) + 1
            percentages = {
                k: int((v / total) * 100)
                for k, v in result_counts.items()
            }

    return render_template("threadline.html",
                           game_id=game_id,
                           user_display=user_display,
                           is_anon=is_anon,
                           comments=comments,
                           insights=insights,
                           matchup_insight=matchup_insight1,
                           batter=batter,
                           pitcher=pitcher,
                           survey=survey,
                           user_vote=user_vote,
                           result_counts=result_counts,
                           percentages=percentages,
                           home_team=home_team,
                           away_team=away_team,
                           scheduled_time=scheduled_time,
                           status=status,
                           sport_icon=sport_icon)


@app.template_filter("timeago")
def timeago(ts):
    if not ts:
        return ""
    now = datetime.now(timezone.utc)
    diff = now - ts
    if diff.days >= 1:
        return f"{diff.days}d ago"
    elif diff.seconds >= 3600:
        return f"{diff.seconds // 3600}h ago"
    elif diff.seconds >= 60:
        return f"{diff.seconds // 60}m ago"
    else:
        return "Just now"


@app.route("/threadline/survey_vote", methods=["POST"])
def record_survey_vote():
    data = request.get_json()
    survey_id = data.get("survey_id")
    selected = data.get("selected_option")

    username = session.get("username") or session.get("anon_name")
    if not username:
        return jsonify({"error": "User not identified"}), 403

    survey = threadline_surveys.find_one({"_id": ObjectId(survey_id)})
    if not survey:
        return jsonify({"error": "Survey not found"}), 404

    # Has user already voted?
    existing_vote = threadline_votes.find_one({
        "survey_id": ObjectId(survey_id),
        "username": username
    })
    if existing_vote:
        return jsonify({"error": "Already voted"}), 400

    # Record vote
    threadline_votes.insert_one({
        "survey_id": ObjectId(survey_id),
        "game_id": survey.get("game_id"),
        "username": username,
        "selected_option": selected,
        "correct_option": survey.get("correct_option"),
        "timestamp": datetime.now(timezone.utc)
    })

    # Update reputation
    correct = (selected == survey.get("correct_option"))
    delta = 1 if correct else -1
    user_reputation.update_one(
        {"username": username},
        {"$inc": {"score": delta}},
        upsert=True
    )

    return jsonify({"success": True, "correct": correct})


@app.route("/threadline")
def threadline_home():
    sport_icons = {
        "baseball": "⚾",
        "basketball": "🏀",
        "football": "🏈",
        "hockey": "🏒",
        "soccer": "⚽"
    }
    today = datetime.now(timezone.utc).date()
    games_today = list(threadline_games.find(
        {"date": str(today)},
        {"_id": 0}
    ).sort([
        ("scheduled_time", 1),
        ("sport", 1)
    ]))

    username = session.get("username") or session.get("anon_name")
    if not username:
        anon = f"Anon-{os.urandom(2).hex()[:4]}"
        session["anon_name"] = anon
        username = anon

    rep = user_reputation.find_one({"username": username}) or {"score": 0}
    for game in games_today:
        game["icon"] = sport_icons.get(game["sport"].lower(), "🎮")
        game_id = game["game_id"]
        game["comment_count"] = threadline_comments.count_documents({
            "game_id": game_id,
            "timestamp": {"$gte": datetime.now(timezone.utc) - timedelta(minutes=30)}
        })
        game["has_survey"] = threadline_surveys.find_one({
            "game_id": game_id
        }) is not None

    return render_template("threadline_home.html",
                           games=games_today,
                           user_display=username,
                           rep_score=rep["score"])


@app.route("/threadline/leaderboard")
def show_leaderboard():
    top_users = list(user_reputation.find().sort("score", -1).limit(10))
    return render_template("leaderboard.html", top_users=top_users)


@app.route("/threadline/top_insights")
def top_insights():
    top = list(threadline_insights.find().sort("votes", -1).limit(10))
    return render_template("top_insights.html", insights=top)


@app.route("/api/leagues")
def list_leagues():
    return jsonify(get_leagues())


@app.route("/api/games/<league_id>")
def league_games(league_id):
    mode = request.args.get("mode", "next")
    games = get_games_for_league(league_id, mode=mode)
    return jsonify(games)


@app.route("/threadline/team/<team_name>")
def team_schedule(team_name):
    today = datetime.now(timezone.utc).date().isoformat()

    upcoming = list(threadline_games.find({
        "$or": [
            {"home_team": team_name},
            {"away_team": team_name}
        ],
        "date": {"$gte": today}
    }, {"_id": 0}).sort("scheduled_time"))

    return render_template("team_schedule.html", team=team_name, games=upcoming)


@app.route("/threadline/game_status/<game_id>")
def fetch_threadline_game_status(game_id):
    game = threadline_games.find_one({"game_id": game_id}, {"_id": 0, "status": 1, "scheduled_time": 1})
    if not game:
        return jsonify({"error": "Game not found"}), 404

    return jsonify({
        "status": game.get("status", "Scheduled"),
        "scheduled_time": game.get("scheduled_time", "TBD")
    })


@app.route("/threadline/game_status/<game_id>")
def get_game_status(game_id):
    game = threadline_games.find_one({"game_id": game_id}, {"_id": 0, "status": 1, "scheduled_time": 1})
    if not game:
        return jsonify({"error": "Game not found"}), 404

    return jsonify({
        "status": game.get("status", "Scheduled"),
        "scheduled_time": game.get("scheduled_time", "TBD")
    })


@app.route("/shop-data")
def get_shop_data():
    import os
    import json
    import re
    import requests
    from urllib.parse import unquote
    from collections import defaultdict

    def slugify(text):
        return re.sub(r"[^\w]+", "-", text.lower()).strip("-")

    def load_tag_config():
        try:
            with open("tag_config.json") as f:
                return json.load(f)
        except Exception:
            return {}

    def auto_tag_product(p, tag_config):
        title = p.get("title", "").lower()
        meta = {
            "slug": slugify(p.get("title", "")),
            "title": p.get("title", ""),
            "tags": [t.lower() for t in p.get("tags", []) if isinstance(t, str)],
            "featured": False,
            "hide": False,
            "type": "shirt",
            "sort_order": 0,
            "seo_description": "",
            "state": "",
            "city": "",
            "sport": "",
            "team": "",
            "collection": "",
            "video_url": "",
            "printify_id": str(p.get("id"))
        }

        for key, values in tag_config.items():
            for val in values:
                if val.lower() in title:
                    meta[key] = val
                    break

        return meta

    token = os.environ.get("PRINTIFY_API_TOKEN")
    shop_id = os.environ.get("PRINTIFY_SHOP_ID")
    url = f"https://api.printify.com/v1/shops/{shop_id}/products.json"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        resp = requests.get(url, headers=headers)
        products = resp.json().get("data", [])

        # Load curated metadata keyed by slug
        try:
            with open("product_tags.json", "r") as f:
                static_metadata = json.load(f)
        except Exception:
            static_metadata = {}

        tag_config = load_tag_config()
        enriched = []
        updated_static = static_metadata.copy()  # for appending new entries

        for p in products:
            title_slug = slugify(p.get("title", ""))
            meta = static_metadata.get(title_slug)

            if meta:
                p.update(meta)
                p["slug"] = meta["slug"]
            else:
                generated = auto_tag_product(p, tag_config)
                p.update(generated)
                updated_static[title_slug] = generated

            enriched.append(p)

        # Write updated metadata back if new entries were added
        if updated_static != static_metadata:
            with open("product_tags.json", "w") as f:
                json.dump(updated_static, f, indent=2)

        # Apply filters from query string
        filters = request.args.to_dict()
        for key, val in filters.items():
            val = unquote(val).strip().lower()
            enriched = [
                p for p in enriched
                if val in str(p.get(key, "")).lower()
                   or any(val in t.lower() for t in p.get("tags", []))
            ]

        return jsonify(enriched)

    except Exception as e:
        print("get_shop_data error:", e)
        return jsonify({"error": str(e)}), 500


def build_navigation_structure(sections):
    from collections import defaultdict

    catalog = defaultdict(list)

    for slug, meta in sections.items():
        # Skip if title/URL are missing
        if not meta.get("title") or not slug:
            continue

        # Use sport or collection as the top-level category
        top_level = meta.get("sport") or meta.get("collection") or "general"
        label = meta["title"]
        url = f"/shop/{slug}"

        catalog[top_level].append({
            "label": label,
            "url": url
        })

    return dict(catalog)


def load_taxonomy():
    try:
        with open("taxonomy.json") as f:
            raw = json.load(f)
        values = {}
        for key, opts in raw.items():
            values[key] = [
                {"value": k, **v}
                for k, v in opts.items()
                if not v.get("hidden")
            ]
            values[key].sort(key=lambda x: x.get("sort", 0))
        return values
    except Exception:
        return {}


def get_available_filter_values(metadata):
    from collections import defaultdict

    filters = defaultdict(set)

    for product in metadata.values():
        for key in ("sport", "city", "collection", "type"):
            if key in product and product[key]:
                filters[key].add(product[key])

    # Optionally: sort results alphabetically
    return {k: sorted(v) for k, v in filters.items()}


def load_tag_rules():
    with open("tag_config.json") as f:
        return json.load(f)

def slugify(text):
    return re.sub(r"[^\w]+", "-", text.lower()).strip("-")

def auto_tag_product(p, tag_rules):
    title = p.get("title", "").lower()
    metadata = {
        "slug": slugify(p.get("title", "")),
        "title": p.get("title", ""),
        "tags": [t.lower() for t in p.get("tags", []) if isinstance(t, str)],
        "featured": False,
        "hide": False
    }

    for key, values in tag_rules.items():
        for value in values:
            if value.lower() in title:
                metadata[key] = value
                break

    return metadata


@app.route("/shop", defaults={"subpath": ""})
@app.route("/shop/<path:subpath>")
def shop(subpath):
    import json

    track_view("/shop")
    parts = [p.lower() for p in subpath.strip("/").split("/")] if subpath else []

    # Extract from subpath first
    filters = {}

    # ... populate filters from path parts like sport/city/etc.

    # Then override with query params (query > path)
    filters = {**filters, **request.args.to_dict()}

    known_keys = {"sport", "city", "collection", "type"}

    for part in parts:
        for key in known_keys:
            if key not in filters and part:
                filters[key] = part

    slug = "-".join(parts)

    # Load page-level metadata and catalog nav
    try:
        with open("sections.json") as f:
            sections = json.load(f)
    except Exception:
        sections = {}

    catalog = build_navigation_structure(sections)
    section_meta = sections.get(slug) or {
        "title": "Shop – First String",
        "description": "Explore bold apparel from the First String collection.",
        "image": "/static/images/seo/default-banner.jpg"
    }

    # Load filter value definitions from taxonomy.json
    def load_taxonomy():
        try:
            with open("taxonomy.json") as f:
                raw = json.load(f)
            values = {}
            for key, items in raw.items():
                filtered = [
                    {"value": k, "label": v.get("label", k), "sort": v.get("sort", 0)}
                    for k, v in items.items()
                    if not v.get("hidden", False)
                ]
                values[key] = sorted(filtered, key=lambda x: x["sort"])
            return values
        except Exception as e:
            print("taxonomy load error:", e)
            return {}

    available_values = load_taxonomy()

    return render_template(
        "shop.html",
        filters=filters,  # ✅ This line ensures filters is available to the template
        subpath=subpath,
        meta=section_meta,
        catalog=catalog,
        sports=sorted(catalog.keys()),
        available_values=available_values,
        nav=load_nav()
    )


def load_nav():
    try:
        with open("nav.json") as f:
            return json.load(f)
    except Exception as e:
        print("Error loading nav.json:", e)
        return []


@app.route("/admin/generate-sections")
def generate_sections_admin():
    try:
        from generate_sections import load_product_tags, generate_sections, save_sections
        products = load_product_tags()
        sections = generate_sections(products)
        save_sections(sections)
        return f"✅ Generated {len(sections)} section entries.", 200
    except Exception as e:
        return f"❌ Error: {str(e)}", 500


@app.route("/admin/sections-editor")
def sections_editor():
    return render_template("sections_editor.html")


@app.route("/shop/<slug>")
def product_detail(slug):
    with open("product_tags.json") as f:
        product_tags = json.load(f)

    product = product_tags.get(slug)

    def hydrate_from_printify(slug, fallback=None):
        pid = fallback.get("printify_id") if fallback else None
        if not pid:
            print(f"❌ No printify_id for slug: {slug}")
            return None

        print(f"🔄 Fetching {slug} from Printify")
        url = f"https://api.printify.com/v1/shops/{SHOP_ID}/products/{pid}.json"
        r = requests.get(url, headers={"Authorization": f"Bearer {PRINTIFY_API_TOKEN}"})
        if r.status_code != 200:
            print(f"❌ Printify fetch failed: {r.status_code}")
            return None

        pdata = r.json()

        # Fallback image logic
        images = []
        for area in pdata.get("print_areas", []):
            for ph in area.get("placeholders", []):
                if ph.get("src"):
                    images.append({"src": ph["src"]})
        if not images:
            images = [{"src": i["src"]} for i in pdata.get("images", []) if i.get("src")]

        # Clean & sort options
        def sort_values(opt):
            vals = [v for v in opt.get("values", []) if v.get("name")]
            if opt.get("name", "").lower() == "size":
                order = ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"]
                vals.sort(key=lambda v: order.index(v["name"]) if v["name"] in order else 999)
            else:
                vals.sort(key=lambda v: v["name"].lower())
            return {"name": opt.get("name"), "type": opt.get("type"), "values": vals}

        options = [sort_values(opt) for opt in pdata.get("options", []) if opt.get("values")]

        hydrated = {
            **(fallback or {}),
            "title": pdata.get("title"),
            "variants": pdata.get("variants", []),
            "options": options,
            "images": images,
        }

        product_tags[slug] = hydrated
        with open("product_tags.json", "w") as f:
            json.dump(product_tags, f, indent=2)
        print(f"✅ Hydrated and cached: {slug}")
        return hydrated

    # Product exists and will be refreshed regardless
    if product:
        product = hydrate_from_printify(slug, fallback=product)
    else:
        # Try to find an entry by slug in unsynced metadata
        with open("product_metadata.json") as meta_f:
            metadata = json.load(meta_f).get(slug)
        if metadata:
            product = hydrate_from_printify(slug, fallback=metadata)

    if not product or product.get("hide"):
        return "Product not found", 404

    if slug != product.get("slug"):
        return redirect(url_for("product_detail", slug=product["slug"]), code=301)

    # Fallback to variant-level images if needed
    if not product.get("images") and product.get("variants"):
        product["images"] = [
            {"src": v["images"][0]["src"]}
            for v in product["variants"]
            if v.get("images")
        ]

    is_admin = request.cookies.get("admin") == "true"
    return render_template("product_detail.html", product=product, is_admin=is_admin)


@app.route("/webhook/printify", methods=["POST"])
def printify_webhook():
    payload = request.get_json()
    event = payload.get("event")
    product_id = payload.get("resource", {}).get("id")

    if event == "product:updated" and product_id:
        hydrate_by_id(product_id)  # you'd define this
        return "✅ Synced", 200

    return "Ignored", 200


@app.route("/admin/sync-products")
@admin_required
def sync_printify_products():
    import subprocess
    try:
        result = subprocess.run(
            ["python3", "sync_printify.py"],  # ✅ updated filename here
            capture_output=True,
            text=True,
            timeout=15
        )
        output = result.stdout or result.stderr
        return f"<pre>{output}</pre>"
    except Exception as e:
        return f"Error running sync: {e}", 500


@app.route("/debug/images/<slug>")
def debug_images(slug):
    with open("product_tags.json") as f:
        product_tags = json.load(f)

    product = next((p for p in product_tags.values() if p.get("slug") == slug), None)
    if not product:
        return {"error": "Product not found"}, 404

    return {
        "slug": slug,
        "has_images": bool(product.get("images")),
        "images": product.get("images"),
        "variants": product.get("variants"),
    }


@app.route("/sections.json")
def get_sections_json():
    with open("sections.json") as f:
        return f.read(), 200, {"Content-Type": "application/json"}

@app.route("/admin/save-sections", methods=["POST"])
def save_sections_json():
    try:
        data = request.get_json()
        with open("sections.json", "w") as f:
            json.dump(data, f, indent=2)
        return "OK", 200
    except Exception as e:
        return f"Error: {str(e)}", 500


@app.route("/admin/ai-rewrite-description", methods=["POST"])
def ai_rewrite_description():
    data = request.json
    title = data.get("title", "")
    existing = data.get("existing", "")
    # Replace with real AI call or logic
    improved = f"{existing} (Updated for clarity and SEO)"
    return improved


@app.route("/admin/available-types")
def available_types():
    try:
        with open("product_tags.json") as f:
            products = json.load(f)
        types = set(
            data.get("type", "").strip()
            for data in products.values()
            if data.get("type")
        )
        return sorted(types)
    except Exception as e:
        return {"error": str(e)}, 500

@app.route("/shop-meta")
def get_shop_meta():
    from urllib.parse import unquote
    try:
        filters = {k: unquote(v).title() for k, v in request.args.items()}
        parts = [filters.get(k) for k in ("city", "sport", "collection", "type") if filters.get(k)]
        slug = "-".join(parts).lower()

        with open("sections.json") as f:
            sections = json.load(f)
        meta = sections.get(slug, {})

        return jsonify({
            "title": meta.get("title") or "Shop – First String",
            "description": meta.get("description") or "Explore bold, fan-driven apparel from the Signature Collection.",
            "image": meta.get("image") or "/static/images/seo/default-banner.jpg"
        })
    except Exception as e:
        print("shop-meta error:", e)
        return jsonify({
            "title": "Shop – First String",
            "description": "Explore bold, fan-driven apparel from the Signature Collection.",
            "image": "/static/images/seo/default-banner.jpg"
        }), 500


if __name__ == "__main__":
    import logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)  # or WARNING to still show 404s, etc.

    app.run(host="0.0.0.0", port=port)