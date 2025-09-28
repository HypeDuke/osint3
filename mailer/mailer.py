import os
import time
import smtplib
import re
from email.mime.text import MIMEText
from elasticsearch import Elasticsearch
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import schedule


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

def load_blacklist(filename="blacklist.txt"):
    if not os.path.exists(filename):
        return []
    with open(filename, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]
    
BLACKLIST = load_blacklist("blacklist.txt")

def is_blacklisted(result_line: str) -> bool:
    """Check nếu 1 dòng kết quả nằm trong blacklist"""
    for b in BLACKLIST:
        if b in result_line:
            return True
    return False
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
        "<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse'>",
        "<thead><tr>"
        "<th>URL</th><th>User</th><th>Pass</th><th>Indexed At (UTC+7)</th>"
        "</tr></thead>",
        "<tbody>"
    ]
    for r in rows:
        link_html = f"<a href='{r['url']}'>{r['url']}</a>" if r.get("url") else "N/A"
        table.append(
            "<tr>"
            f"<td>{link_html}</td>"
            f"<td>{r.get('user','')}</td>"
            f"<td>{r.get('pass','')}</td>"
            f"<td>{r.get('indexed_at','')}</td>"
            "</tr>"
        )
    table.append("</tbody></table>")
    return "\n".join(table)

# Add subdomain fectcher
def fetch_subdomains(domain):
    url = f"https://viewdns.info/subdomains/?domain={domain}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept-Language": "en-US,en;q=0.9"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"[!] Error fetching subdomains: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.find_all("tr")

    results = []
    for row in rows:
        cols = row.find_all("td")
        if len(cols) >= 3:
            subdomain = cols[0].get_text(strip=True)

            ip_html = cols[1]
            ips = [ip.strip() for ip in ip_html.stripped_strings if ip.strip()]
            if not ips:
                ips = ["No IP Address"]

            date_html = cols[2]
            dates = [d.strip() for d in date_html.stripped_strings if d.strip()]
            if not dates:
                dates = ["N/A"]

            max_len = max(len(ips), len(dates))
            for i in range(max_len):
                ip = ips[i] if i < len(ips) else ips[-1]
                date = dates[i] if i < len(dates) else dates[-1]
                results.append([subdomain, ip, date])
    return results

def weekly_subdomain_task():
    DOMAIN = os.getenv("TARGET_DOMAIN", "napas.com.vn")
    print(f"[*] Running weekly subdomain fetch for {DOMAIN}...")
    results = fetch_subdomains(DOMAIN)
    if results:
        html = build_subdomain_html(results, DOMAIN)
        send_mail_html(f"🕵️ Weekly Subdomain Report for {DOMAIN}", html)
    else:
        print("[*] No subdomains found")


def build_subdomain_html(rows, domain):
    html = [
        f"<h3>Weekly Subdomain Report for {domain}</h3>",
        "<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse'>",
        "<thead><tr><th>Subdomain</th><th>IP</th><th>Date</th></tr></thead>",
        "<tbody>"
    ]
    for r in rows:
        html.append(f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td></tr>")
    html.append("</tbody></table>")
    return "\n".join(html)


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

            # Bỏ qua nếu line/url trùng blacklist
            if any(b.lower() in line.lower() or b.lower() in url_field.lower() for b in BLACKLIST):
                print(f"[DEBUG] Doc {doc_id} bị loại vì trùng blacklist")
                seen_ids.add(doc_id)
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
                "url": link,
                "user": user,
                "pass": passwd,
                "indexed_at": indexed_human
               
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
    
    # Chạy ngay khi container start
    weekly_subdomain_task()
    # Force test mail on startup
    #send_mail_html("🚨 Test Mail", "<b>This is a test alert from Mailer service</b>")
     # Đặt lịch chạy mỗi thứ 2 lúc 09:00 sáng
    schedule.every().monday.at("09:00").do(weekly_subdomain_task)


    while True:
        check_new_data()
        schedule.run_pending() # kiểm tra xem có job subdomain nào đến hạn không
        time.sleep(60)
