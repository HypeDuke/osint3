import os
import time
import smtplib
from email.mime.text import MIMEText
from elasticsearch import Elasticsearch
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

ES_HOST = os.getenv("ES_HOST", "http://elasticsearch:9200")
INDEX = os.getenv("ES_INDEX", "osint-results")

FROM_EMAIL = os.getenv("FROM_EMAIL")
FROM_PASS = os.getenv("FROM_PASS")
TO_EMAILS = [e.strip() for e in os.getenv("TO_EMAIL", "").split(",") if e.strip()]

# Load keywords from file
def load_keywords(file_path="keywords.txt"):
    if not os.path.exists(file_path):
        print(f"[!] Keyword file '{file_path}' not found, using empty list.")
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return [line.strip().lower() for line in f if line.strip()]

ALERT_KEYWORDS = load_keywords("keywords.txt")

print(f"[*] Starting Mailer")
print(f"[*] ES_HOST={ES_HOST}, INDEX={INDEX}")
print(f"[*] FROM_EMAIL={FROM_EMAIL}, TO_EMAILS={TO_EMAILS}")
print(f"[*] ALERT_KEYWORDS={ALERT_KEYWORDS}")

# Connect to Elasticsearch
try:
    es = Elasticsearch(ES_HOST)
    if es.ping():
        print("[+] Connected to Elasticsearch")
    else:
        print("[!] Cannot ping Elasticsearch")
except Exception as e:
    print(f"[!] Error connecting to ES: {e}")
    es = None

# Track already alerted docs
seen_ids = set()

def send_mail(subject, body):
    """Send email using Gmail SMTP."""
    print(f"[*] Preparing to send email: {subject}")
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL
    msg["To"] = ", ".join(TO_EMAILS)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(FROM_EMAIL, FROM_PASS)
            server.sendmail(FROM_EMAIL, TO_EMAILS, msg.as_string())
        print(f"[+] Mail sent to {', '.join(TO_EMAILS)}")
    except Exception as e:
        print(f"[!] Error sending mail: {e}")

def check_new_data():
    """Check ES for new docs and send alerts if keywords found."""
    if not es:
        print("[!] ES client not initialized, skipping check.")
        return

    try:
        print("[*] Querying Elasticsearch...")
        resp = es.search(
            index=INDEX,
            body={
                "query": {"match_all": {}},
                "sort": [{"indexed_at": {"order": "desc"}}],
                "size": 20
            }
        )

        hits = resp.get("hits", {}).get("hits", [])
        print(f"[*] Got {len(hits)} docs from ES")

        for h in hits:
            doc_id = h["_id"]
            src = h["_source"]

            line = (src.get("line") or "").lower()
            url = (src.get("url") or "").lower()
            content = (src.get("content") or "").lower()

            print(f"    [-] Checking doc {doc_id} with line='{line[:50]}'...")

            if doc_id not in seen_ids and any(kw in line or kw in url or kw in content for kw in ALERT_KEYWORDS):
                seen_ids.add(doc_id)

                subject = f"🚨 Leak Alert - {src.get('path', 'Unknown')}"
                body = f"""
New possible leaked data detected in Elasticsearch:

📄 Path: {src.get('path', 'N/A')}
🔑 Keyword matched: {','.join([kw for kw in ALERT_KEYWORDS if kw in line or kw in url or kw in content])}
📝 Line: {src.get('line', 'N/A')}
🔗 URL: {src.get('url', 'N/A')}
⏰ Indexed at: {src.get('indexed_at', 'N/A')}
                """
                send_mail(subject, body.strip())
            else:
                print(f"    [-] No keyword match or already seen.")

    except Exception as e:
        print(f"[!] Error querying ES: {e}")

if __name__ == "__main__":
    print("[*] Mailer service started, watching for new OSINT data...")
    while True:
        check_new_data()
        time.sleep(30)  # check every 30 seconds
