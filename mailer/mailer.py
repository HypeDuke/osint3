import os
import time
import smtplib
from email.mime.text import MIMEText
from elasticsearch import Elasticsearch
from dotenv import load_dotenv

# Load env vars
load_dotenv()

ES_HOST = os.getenv("ES_HOST", "http://elasticsearch:9200")
FROM_EMAIL = os.getenv("FROM_EMAIL")
FROM_PASS = os.getenv("FROM_PASS")
TO_EMAILS = [e.strip() for e in os.getenv("TO_EMAIL", "").split(",") if e.strip()]

INDEX = os.getenv("ES_INDEX", "osint-results")

# Connect to Elasticsearch
es = Elasticsearch(ES_HOST)

# Keep track of already seen docs
seen_ids = set()

def send_mail(subject, body):
    """Send email using Gmail SMTP."""
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL
    msg["To"] = ", ".join(TO_EMAILS)  # show all in email header


    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(FROM_EMAIL, FROM_PASS)
            server.sendmail(FROM_EMAIL, TO_EMAILS, msg.as_string())
        print(f"[+] Mail sent to {', '.join(TO_EMAILS)}")
    except Exception as e:
        print(f"[!] Error sending mail: {e}")

def check_new_data():
    """Check ES for new docs and send alerts."""
    try:
        resp = es.search(
            index=INDEX,
            body={
                "query": {"match_all": {}},
                "sort": [{"@timestamp": {"order": "desc"}}],
                "size": 5
            }
        )

        hits = resp.get("hits", {}).get("hits", [])
        for h in hits:
            doc_id = h["_id"]
            if doc_id not in seen_ids:
                seen_ids.add(doc_id)
                src = h["_source"]
                subject = f"🚨 New OSINT Alert - {src.get('source', 'Unknown')}"
                body = f"""
New data detected in Elasticsearch:

🔑 Keyword: {src.get('keyword', 'N/A')}
📝 Content: {src.get('content', 'N/A')}
🔗 URL: {src.get('url', 'N/A')}
⏰ Timestamp: {src.get('timestamp', 'N/A')}
                """
                send_mail(subject, body.strip())
    except Exception as e:
        print(f"[!] Error querying ES: {e}")

if __name__ == "__main__":
    print("[*] Mailer service started, watching for new OSINT data...")
    while True:
        check_new_data()
        time.sleep(60)  # check every 1 minute
