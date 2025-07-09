import os
from pymongo import MongoClient

# Connect to MongoDB using Railway-provided URI
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo:MXQDxgcJWYBgTFtLPiwGdsnRXTIONzNc@trolley.proxy.rlwy.net:25766")
client = MongoClient(MONGO_URI)

# MLB stats DB
mlb_db = client["mlb_stats"]

# First String users DB
users_db = client["first_string_users"]

# Threadline DB
threadline_db = client["threadline"]

# Products DB
product_db = client["products"]

# Collections
product_edits = product_db["product_edits"]
