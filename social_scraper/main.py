import os
import time
import requests
import schedule
from elasticsearch import Elasticsearch
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, request, jsonify
import yaml
import threading

# Load biến môi trường
load_dotenv()
ELASTIC_HOST = os.getenv("ELASTIC_HOST", "http://elasticsearch:9200")
es = Elasticsearch(ELASTIC_HOST)

# ----- API KEY -----
def load_api_key(path="/app/api-keys.yaml"):
    if not os.path.exists(path):
        raise FileNotFoundError(f"API key file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config.get("rapidapi", {}).get("key")

RAPIDAPI_KEY = load_api_key()
HEADERS_BASE = {
    "x-rapidapi-key": RAPIDAPI_KEY
}

# ----- Cấu hình API -----
APIS = {
    "facebook": {
        "base_url": "https://facebook-scraper3.p.rapidapi.com/search/posts?query={query}",
        "host": "facebook-scraper3.p.rapidapi.com"
    }
    # Có thể thêm twitter, reddit...
}

# ----- Load keywords -----
def load_keywords(filename="keywords.txt"):
    if not os.path.exists(filename):
        return []
    with open(filename, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

# ----- Extract content -----
def extract_content(api_name, data):
    results = []
    if not data:
        return results

    try:
        if api_name == "facebook":
            for item in data.get("results", []):
                results.append({
                    "id": item.get("post_id"),
                    "url": item.get("url"),
                    "content": item.get("message"),
                    "timestamp": item.get("timestamp")
                })
        elif api_name == "twitter":
            for item in data.get("results", []):
                results.append({
                    "id": item.get("tweet_id"),
                    "url": item.get("tweet_url"),
                    "content": item.get("text"),
                    "timestamp": item.get("timestamp")
                })
        elif api_name == "reddit":
            for item in data.get("posts", []):
                results.append({
                    "id": item.get("post_id"),
                    "url": item.get("postLink"),
                    "content": item.get("title"),
                    "timestamp": item.get("timestamp")
                })
    except Exception as e:
        print(f"[!] Extract error for {api_name}: {e}")

    return results

# ----- Fetch & Store -----
def fetch_and_store(api_name, api_data, keyword):
    headers = dict(HEADERS_BASE)
    headers["x-rapidapi-host"] = api_data["host"]

    url = api_data["base_url"].format(query=keyword)

    try:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()

        extracted = extract_content(api_name, data)

        for record in extracted:
            doc = {
                "source": api_name,
                "keyword": keyword,
                "timestamp": record.get("timestamp", datetime.now().isoformat()),
                "id": record.get("id"),
                "url": record.get("url"),
                "content": record.get("content")
            }
            es.index(index="social_data", document=doc)

        print(f"[+] Stored {len(extracted)} records from {api_name} ({keyword})")
    except Exception as e:
        print(f"[!] Error fetching {api_name} with keyword '{keyword}': {e}")

# ----- Job định kỳ -----
def job():
    keywords = load_keywords()
    if not keywords:
        print("[!] No keywords found.")
        return

    for keyword in keywords:
        for api_name, api_data in APIS.items():
            fetch_and_store(api_name, api_data, keyword)

# ----- Chạy ngay khi start -----
job()

# ----- Lên lịch chạy mỗi tuần -----
schedule.every(7).days.do(job)

# ----- Flask API -----
app = Flask(__name__)

@app.route("/social", methods=["GET"])
def search_social():
    keyword = request.args.get("keyword", "")
    limit = int(request.args.get("limit", 10))

    if not keyword:
        return jsonify({"error": "Missing keyword"}), 400

    try:
        body = {
            "query": {
                "wildcard": {
                    "content": {   
                        "value": f"*{keyword}*",
                        "case_insensitive": True
                    }
                }
            },
            "size": limit
        }
        resp = es.search(index="social_data", body=body)
        hits = resp.get("hits", {}).get("hits", [])

        results = [
            {
                "source": h["_source"]["source"],
                "keyword": h["_source"]["keyword"],
                "content": h["_source"]["content"],
                "url": h["_source"]["url"],
                "timestamp": h["_source"]["timestamp"]
            }
            for h in hits
        ]
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # chạy schedule trong thread riêng
    def scheduler_thread():
        while True:
            schedule.run_pending()
            time.sleep(60)

    t = threading.Thread(target=scheduler_thread, daemon=True)
    t.start()

    # expose API cho bot
    app.run(host="0.0.0.0", port=5200)
