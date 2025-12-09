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


# ============= DATA MASKING FUNCTIONS =============

def mask_email(email):
    """
    Mask email address - keep first 1-2 chars and everything after @
    Examples:
        thang@abc.com.vn -> th**g@abc.com.vn
        a@test.com -> a*@test.com
        ab@test.com -> ab*@test.com
    """
    if not email or '@' not in email:
        return email
    
    local, domain = email.split('@', 1)
    
    if len(local) <= 1:
        # Single character: a -> a*
        masked_local = local[0] + '*'
    elif len(local) == 2:
        # Two characters: ab -> ab*
        masked_local = local + '*'
    elif len(local) == 3:
        # Three characters: abc -> ab*c
        masked_local = local[0:2] + '*' + local[-1]
    else:
        # More than 3: show first 2 and last 1, mask the rest
        # thang -> th**g
        mask_count = len(local) - 3
        masked_local = local[0:2] + '*' * mask_count + local[-1]
    
    return f"{masked_local}@{domain}"


def mask_password(password):
    """
    Completely mask password with asterisks
    Examples:
        password123 -> ***********
        abc -> ***
    """
    if not password:
        return ""
    return '*' * len(password)


def mask_username(username):
    """
    Mask username that's not an email
    Examples:
        napas_kkepa03 -> na*********3
        thaohp -> th***p
        Aa56456=# -> Aa*****#
    """
    if not username:
        return username
    
    # Check if it's an email
    if '@' in username:
        return mask_email(username)
    
    # For non-email usernames
    if len(username) <= 2:
        return '*' * len(username)
    elif len(username) == 3:
        return username[0] + '*' + username[-1]
    else:
        # Show first 2 and last 1, mask the rest
        mask_count = len(username) - 3
        return username[0:2] + '*' * mask_count + username[-1]


def mask_sensitive_data(text):
    """
    Mask any email or password-like patterns in text
    """
    if not text:
        return text
    
    # Mask emails in text
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    
    def replace_email(match):
        return mask_email(match.group(0))
    
    result = re.sub(email_pattern, replace_email, text)
    return result

# ==================================================

 
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
    """Build HTML table with masked sensitive data"""
    if not rows:
        return "<p>No data to display.</p>"
    
    table = [
        "<table border='1' cellpadding='8' cellspacing='0' style='border-collapse:collapse; font-family: Arial, sans-serif; width: 100%;'>",
        "<thead><tr style='background-color: #f2f2f2;'>"
        "<th style='padding: 10px;'>URL</th>"
        "<th style='padding: 10px;'>User (Masked)</th>"
        "<th style='padding: 10px;'>Pass (Masked)</th>"
        "<th style='padding: 10px;'>Indexed At (UTC+7)</th>"
        "</tr></thead>",
        "<tbody>"
    ]
    
    for r in rows:
        # CRITICAL: Apply masking here
        user_raw = r.get('user', '')
        pass_raw = r.get('pass', '')
        
        # Determine if user is email or username and mask accordingly
        if user_raw:
            if '@' in user_raw:
                masked_user = mask_email(user_raw)
            else:
                masked_user = mask_username(user_raw)
        else:
            masked_user = 'N/A'
        
        # Always fully mask passwords
        masked_pass = mask_password(pass_raw) if pass_raw else 'N/A'
        
        # Build clickable link
        url = r.get('url', '')
        if url and url.startswith('http'):
            link_html = f"<a href='{url}' style='color: #0066cc; word-break: break-all;'>{url}</a>"
        else:
            link_html = url if url else "N/A"
        
        table.append(
            "<tr style='border-bottom: 1px solid #ddd;'>"
            f"<td style='padding: 8px; word-break: break-all;'>{link_html}</td>"
            f"<td style='padding: 8px; font-family: monospace;'>{masked_user}</td>"
            f"<td style='padding: 8px; font-family: monospace;'>{masked_pass}</td>"
            f"<td style='padding: 8px;'>{r.get('indexed_at','N/A')}</td>"
            "</tr>"
        )
    
    table.append("</tbody></table>")
    
    # Add disclaimer
    disclaimer = """
    <div style='margin-top: 20px; padding: 15px; background-color: #fff3cd; border-left: 4px solid #ffc107; font-size: 12px;'>
        <strong>⚠️ Security Notice:</strong><br>
        User credentials have been masked for security purposes.<br>
        • Emails: First 2 characters shown, rest masked (e.g., th**g@domain.com)<br>
        • Usernames: First 2 and last 1 character shown (e.g., na*********3)<br>
        • Passwords: Completely masked with asterisks (******)<br>
        Full details are available in the secure Elasticsearch database.
    </div>
    """
    
    return "\n".join(table) + disclaimer
 
def send_mail_html(subject, html_body):
    if not FROM_EMAIL or not FROM_PASS or not TO_EMAILS:
        print("[!] Missing FROM_EMAIL, FROM_PASS or TO_EMAIL in environment")
        return False
   
    # Wrap content in a nice HTML template
    full_html = f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
                border-radius: 8px 8px 0 0;
                text-align: center;
            }}
            .content {{
                background: white;
                padding: 20px;
                border: 1px solid #ddd;
                border-radius: 0 0 8px 8px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1 style="margin: 0;">🚨 OSINT Leak Alert</h1>
            <p style="margin: 5px 0 0 0; opacity: 0.9;">Security Monitoring System</p>
        </div>
        <div class="content">
            {html_body}
        </div>
    </body>
    </html>
    """
    
    msg = MIMEText(full_html, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL
    msg["To"] = ", ".join(TO_EMAILS)
 
    try:
        print("[DEBUG] Connecting to Gmail SMTP...")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(FROM_EMAIL, FROM_PASS)
            server.sendmail(FROM_EMAIL, TO_EMAILS, msg.as_string())
        print(f"[+] Alert email sent to {', '.join(TO_EMAILS)}")
        print(f"[+] Email contained {len(TO_EMAILS)} recipient(s) with MASKED data")
        return True
    except Exception as e:
        print(f"[!] Error sending email: {e}")
        return False
 
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
 
            print(f"[DEBUG] Checking doc {doc_id}: line={line[:50]}...")
 
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
 
            # Store RAW data here - masking will happen in build_html_table()
            new_rows.append({
                "url": link,
                "user": user,
                "pass": passwd,
                "indexed_at": indexed_human
            })
            
            print(f"[DEBUG] Added row: url={link}, user=***MASKED***, pass=***MASKED***")
 
            seen_ids.add(doc_id)
 
        if new_rows:
            print(f"[*] Found {len(new_rows)} new matching items to alert")
            subject = f"🚨 OSINT Leak Alert - {len(new_rows)} items"
            
            # CRITICAL: This function handles masking
            html = build_html_table(new_rows)
            
            # Verify masking occurred (debug check)
            if any(row.get('user', '') and not any(c == '*' for c in str(row.get('user', ''))) for row in new_rows):
                print("[WARNING] Raw data detected in rows - masking should occur in HTML generation")
            
            send_mail_html(subject, html)
        else:
            print("[*] No new matching rows to alert.")
    except Exception as e:
        print(f"[!] Error querying ES: {e}")
        import traceback
        traceback.print_exc()
 
if __name__ == "__main__":
    print("[*] Mailer service started, watching for new OSINT data...")
    print("[*] Data masking enabled:")
    print("    - Emails: First 2 chars visible (e.g., th**g@abc.com.vn)")
    print("    - Usernames: First 2 and last 1 char visible (e.g., na*********3)")
    print("    - Passwords: Fully masked (******)")
 
    # Test masking functions
    print("\n[TEST] Masking examples:")
    print(f"    thang@abc.com.vn -> {mask_email('thang@abc.com.vn')}")
    print(f"    lukas.drastik@gmail.com -> {mask_email('lukas.drastik@gmail.com')}")
    print(f"    napas_kkepa03 -> {mask_username('napas_kkepa03')}")
    print(f"    thaohp -> {mask_username('thaohp')}")
    print(f"    password123 -> {mask_password('password123')}")
    print(f"    Vtdshn@2022 -> {mask_password('Vtdshn@2022')}")
    print()
 
    # Force test mail on startup (optional - uncomment to test)
    # test_rows = [
    #     {"url": "https://test.com", "user": "test@example.com", "pass": "password123", "indexed_at": "2024-01-01"}
    # ]
    # send_mail_html("🧪 Test Mail with Masking", build_html_table(test_rows))
 
    while True:
        check_new_data()
        time.sleep(60)