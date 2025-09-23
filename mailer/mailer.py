import os
import time
import smtplib
import re
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

print("[DEBUG] FROM_EMAIL:", FROM_EMAIL)
print("[DEBUG] TO_EMAILS:", TO_EMAILS)
print("[DEBUG] ES_HOST:", ES_HOST)
print("[DEBUG] INDEX:", INDEX)

# Load keywords from file
def load_keywords(file_path="keywords.txt"):
    if not os.path.exists(file_path):
        print(f"[!] Keyword file '{file_path}' not found, using empty list.")
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        kws = [line.strip().lower() for line in f if line.strip()]
    print(f"[+] Loaded {len(kws)} keywords from {file_path}: {kws}")
    return kws

ALERT_KEYWORDS = load_keywords("keywords.txt")

# Connect to Elasticsearch
es = Elasticsearch(ES_HOST)

# Track already alerted docs (in-memory)
seen_ids = set()

# helper: parse a leak line into (link, user, pass)
def parse_leak_line(line: str):
    line = line.strip()
    if not line.lower().startswith("http"):
        return (None, None, None)

    m = re.match(r"^(https?://[^\s:]+(?::\d+)?[^\s]*?)(?::([^:]+))?(?::([^:]+))?$", line)
    if m:
        url = m.group(1)
        user = m.group(2) or ""
        passwd = m.group(3) or ""
        return (url, user, passwd)
    return (line, "", "")

def build_html_table(rows):
    table = [
        "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse'>",
        "<thead><tr>"
        "<th>Path</th><th>Keyword matched</th><th>Link</th><th>User</th><th>Pass</th><th>Indexed At (UTC+7)</th>"
        "</tr></thead>",
        "<tbody>"
    ]
    for r in rows:
        link_html = f"<a href='{r['url']}'>{r['url']}</a>" if r.get("url") else "N/A"
        table.append(
            "<tr>"
            f"<td>{r.get('path','')}</td>"
            f"<td>{r.get('keyword','')}</td>"
            f"<td>{link_html}</td>"
            f"<td>{r.get('user','')}</td>"
            f"<td>{r.get('pass','')}</td>"
            f"<td>{r.get('indexed_at','')}</td>"
            "</tr>"
        )
    table.append("</tbody></table>")
    return "\n".join(table)

def send_mail_html(subject, html_body):
    if not FROM_EMAIL or not FROM_PASS or not TO_EMAILS:
        print("[!] Missing FROM_EMAIL, FROM_PASS or TO_EMAIL in environment")
        return False
    
    msg = MIMEText(html_body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL
    msg["To"] = ", ".join(TO_EMAILS)

    try:
        print("[DEBUG] Connecting to Gmail SMTP...")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(FROM_EMAIL, FROM_PASS)
            server.sendmail(FROM_EMAIL, TO_EMAILS, msg.as_string())
        print(f"[+] Alert email sent to {', '.join(TO_EMAILS)}")
    except Exception as e:
        print(f"[!] Error sending email: {e}")

def check_new_data():
    try:
        resp = es.search(
            index=INDEX,
            body={
                "query": {"match_all": {}},
                "sort": [{"indexed_at": {"order": "desc"}}],
                "size": 50
            }
        )
        hits = resp.get("hits", {}).get("hits", [])
        print(f"[DEBUG] Retrieved {len(hits)} docs from ES")

        new_rows = []
        for h in hits:
            doc_id = h["_id"]
            src = h["_source"]
            line = (src.get("line") or src.get("content") or "").strip()
            url_field = src.get("url") or ""
            path = src.get("path") or ""

            print(f"[DEBUG] Checking doc {doc_id}: line={line}, url={url_field}")

            if doc_id in seen_ids:
                continue

            keyword_matches = [kw for kw in ALERT_KEYWORDS if kw in line.lower() or kw in url_field.lower()]
            print(f"[DEBUG] Keyword matches for {doc_id}: {keyword_matches}")

            if not keyword_matches:
                seen_ids.add(doc_id)
                continue

            link, user, passwd = parse_leak_line(line)
            if not link and url_field:
                link = url_field

            indexed_ts = src.get("indexed_at") or src.get("timestamp") or ""
            indexed_human = str(indexed_ts)

            new_rows.append({
                "path": path,
                "keyword": ",".join(keyword_matches),
                "content": line,
                "url": link,
                "user": user,
                "pass": passwd,
                "indexed_at": indexed_human,
                "doc_id": doc_id
            })

            seen_ids.add(doc_id)

        if new_rows:
            subject = f"🚨 OSINT Leak Alert - {len(new_rows)} items"
            html = build_html_table(new_rows)
            send_mail_html(subject, html)
        else:
            print("[*] No new matching rows to alert.")
    except Exception as e:
        print(f"[!] Error querying ES: {e}")

if __name__ == "__main__":
    print("[*] Mailer service started, watching for new OSINT data...")

    # Force test mail on startup
    send_mail_html("🚨 Test Mail", "<b>This is a test alert from Mailer service</b>")

    while True:
        check_new_data()
        time.sleep(60)
