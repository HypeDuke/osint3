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

def parse_leak_line(text: str):
    """
    Try to extract link, user, pass from the given text.
    Returns tuple (link, user, password) where each can be None.
    Heuristics:
      - If there's an URL, take it as link. If URL is followed by :token1:token2 style, treat token1/token2 as user/pass.
      - Else, try to find pattern token1:token2 (and token lengths reasonable).
    """
    if not text:
        return (None, None, None)
    text = text.strip()
    # find url
    m = URL_RE.search(text)
    if m:
        link = m.group(1).rstrip('.,;')
        # look for trailing :user:pass after the url in the original text
        after = text[m.end():].lstrip()
        # common patterns: :Bank:12345 or :user:pass
        # remove leading punctuation/spaces
        if after.startswith(':'):
            parts = after.split(':')
            # parts[0] == '' because string begins with ':'
            parts = [p for p in parts if p != '']
            if len(parts) >= 2:
                user = parts[0]
                passwd = parts[1]
                return (link, user, passwd)
            elif len(parts) == 1:
                # maybe only one token after colon, treat as password
                return (link, None, parts[0])
        # also sometimes the url itself contains colon-separated fragments (e.g. https://...:bank:1234)
        # try to parse tokens attached to the url text (no space)
        tail = None
        tail_match = re.search(r'(https?://[^\s,;]+(:[^:\s,;]+){1,2})', text)
        if tail_match:
            combined = tail_match.group(1)
            # split by ':' from the end
            if combined.count(':') >= 2:
                # split into url, user, pass
                parts = combined.split(':')
                # reconstruct url up to "https://.../..." (first part may include scheme+host+path)
                url_part = parts[0]
                rest = parts[1:]
                if len(rest) >= 2:
                    return (url_part, rest[0], rest[1])
        # fallback
        return (link, None, None)
    else:
        # no url -> try user:pass pattern
        # find token:token with moderate lengths
        pair = re.search(r'([A-Za-z0-9._%+-]{1,64}):([A-Za-z0-9._%+-@]{1,128})', text)
        if pair:
            return (None, pair.group(1), pair.group(2))
    return (None, None, None)


def send_mail_html(subject, html_body):
    """Send email with HTML body using Gmail SMTP (SSL)."""
    msg = MIMEText(html_body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL
    msg["To"] = ", ".join(TO_EMAILS)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(FROM_EMAIL, FROM_PASS)
            server.sendmail(FROM_EMAIL, TO_EMAILS, msg.as_string())
        print(f"[+] Mail sent to {', '.join(TO_EMAILS)}")
    except Exception as e:
        print(f"[!] Error sending mail: {e}")


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
            subject = f"🚨 OSINT Leak Batch Alert - {len(new_rows)} items"
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
