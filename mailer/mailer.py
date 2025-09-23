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

# Load keywords from file
def load_keywords(file_path="keywords.txt"):
    if not os.path.exists(file_path):
        print(f"[!] Keyword file '{file_path}' not found, using empty list.")
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        kws = [line.strip().lower() for line in f if line.strip()]
    print(f"[+] Loaded {len(kws)} keywords from {file_path}")
    return kws

ALERT_KEYWORDS = load_keywords("keywords.txt")

# Connect to Elasticsearch
es = Elasticsearch(ES_HOST)

# Track already alerted docs (in-memory)
seen_ids = set()

# helper: parse a leak line into (link, user, pass)
URL_RE = re.compile(r'(https?://[^\s,;]+)', re.IGNORECASE)

def parse_leak_line(line: str):
    """
    Parse leaked line into (url, user, pass).
    Supports:
      https://host/path:user:pass
      https://host/path:user
    """
    line = line.strip()
    if not line.lower().startswith("http"):
        return (None, None, None)

    # Regex: URL + optional user + optional pass
    m = re.match(r"^(https?://[^\s:]+(?::\d+)?[^\s]*?)(?::([^:]+))?(?::([^:]+))?$", line)
    if m:
        url = m.group(1)
        user = m.group(2) or ""
        passwd = m.group(3) or ""
        return (url, user, passwd)
    return (line, "", "")

def build_html_table(rows):
    """rows is list of dicts with keys: path, keyword, content, url, user, pass, indexed_at"""
    
    table = [
        "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse'>",
        "<thead><tr>"
        "<th>Path</th><th>Keyword matched</th><th>Link</th><th>User</th><th>Pass</th><th>Indexed At (UTC+7)</th>"
        "</tr></thead>",
        "<tbody>"
    ]
    for r in rows:
        link_html = f"<a href='{r['url']}'>{r['url']}</a>" if r.get("url") else "N/A"
        user = r.get("user") or ""
        passwd = r.get("pass") or ""
        indexed = r.get("indexed_at") or ""
        table.append(
            "<tr>"
            f"<td>{r.get('path','')}</td>"
            f"<td>{r.get('keyword','')}</td>"
            f"<td>{link_html}</td>"
            f"<td>{user}</td>"
            f"<td>{passwd}</td>"
            f"<td>{indexed}</td>"
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
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(FROM_EMAIL, FROM_PASS)
            server.sendmail(FROM_EMAIL, TO_EMAILS, msg.as_string())
        print(f"[+] Alert email sent to {', '.join(TO_EMAILS)}")
    except Exception as e:
        print(f"[!] Error sending email: {e}")


def check_new_data():
    """Check ES for new docs and send one batched email if matches found."""
    try:
        # fetch recent docs (size adjustable)
        resp = es.search(
            index=INDEX,
            body={
                "query": {"match_all": {}},
                "sort": [{"indexed_at": {"order": "desc"}}],
                "size": 50
            }
        )
        hits = resp.get("hits", {}).get("hits", [])
        new_rows = []
        for h in hits:
            doc_id = h["_id"]
            if doc_id in seen_ids:
                continue
            src = h["_source"]
            line = (src.get("line") or src.get("content") or "").strip()
            url_field = src.get("url") or ""
            path = src.get("path") or ""
            keyword_matches = []
            # check keywords in line or url
            for kw in ALERT_KEYWORDS:
                if kw and (kw in line.lower() or kw in url_field.lower()):
                    keyword_matches.append(kw)
            if not keyword_matches:
                # no keyword matched -> skip (but mark as seen so it won't be reprocessed)
                seen_ids.add(doc_id)
                continue

            # parse line for link/user/pass
            link, user, passwd = parse_leak_line(line)
            # if no link found but there is url field in _source, prefer that
            if not link and url_field:
                link = url_field

            # convert indexed_at (epoch) to readable UTC+7 if present
            indexed_ts = src.get("indexed_at") or src.get("timestamp") or ""
            indexed_human = ""
            try:
                if isinstance(indexed_ts, (int, float)):
                    # utcfromtimestamp then add 7 hours
                    from datetime import datetime, timedelta
                    dt = datetime.utcfromtimestamp(int(indexed_ts)) + timedelta(hours=7)
                    indexed_human = dt.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    indexed_human = str(indexed_ts)
            except Exception:
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

            # mark as seen (so next run won't resend)
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
    # simple loop, tune sleep interval as needed
    while True:
        check_new_data()
        time.sleep(60)
