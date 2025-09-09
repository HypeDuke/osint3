import os
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

FROM_EMAIL = os.getenv("FROM_EMAIL")
FROM_PASS = os.getenv("FROM_PASS")
TO_EMAIL = os.getenv("TO_EMAIL")

def send_mail(subject, body):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL
    msg["To"] = TO_EMAIL

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(FROM_EMAIL, FROM_PASS)
            server.sendmail(FROM_EMAIL, [TO_EMAIL], msg.as_string())
        print("[+] Test mail dk sent successfully")
    except Exception as e:
        print(f"[!] Error: {e}")

if __name__ == "__main__":
    send_mail("🚀 Test Email", "This is a test from the mailer container.")
