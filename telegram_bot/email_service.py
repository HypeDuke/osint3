"""
Email Service Module
Handles all email sending functionality
"""
import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Email credentials
EMAIL_FROM = os.getenv('EMAIL_FROM')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
EMAIL_TO = os.getenv('EMAIL_TO')
HC_EMAIL_TO = os.getenv('HC_EMAIL_TO')
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '465'))


class EmailService:
    """Service for sending emails"""
    
    @staticmethod
    def send_email(subject, html_content, to_emails=None):
        """
        Send email with HTML content
        
        Args:
            subject: Email subject
            html_content: HTML body content
            to_emails: List of recipient emails (default: EMAIL_TO from env)
        
        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not EMAIL_FROM or not EMAIL_PASSWORD:
            print("[!] Missing EMAIL_FROM or EMAIL_PASSWORD in environment")
            return False
        
        if to_emails is None:
            if not EMAIL_TO:
                print("[!] Missing EMAIL_TO in environment")
                return False
            to_emails = [email.strip() for email in EMAIL_TO.split(',')]
        
        try:
            msg = MIMEText(html_content, "html", "utf-8")
            msg["Subject"] = subject
            msg["From"] = EMAIL_FROM
            msg["To"] = ", ".join(to_emails)
            
            print(f"[DEBUG] Connecting to {SMTP_SERVER}:{SMTP_PORT}...")
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
                server.login(EMAIL_FROM, EMAIL_PASSWORD)
                server.sendmail(EMAIL_FROM, to_emails, msg.as_string())
            
            print(f"      ✅ Email sent to {', '.join(to_emails)}")
            return True
        except Exception as e:
            print(f"      ❌ Email error: {e}")
            return False
    
    @staticmethod
    def send_health_check_email(status="success", message=""):
        """
        Send health check notification email
        
        Args:
            status: "success" or "failed"
            message: Status message
        """
        if not EMAIL_FROM or not EMAIL_PASSWORD or not HC_EMAIL_TO:
            return
        
        try:
            status_color = "#28a745" if status == "success" else "#dc3545"
            status_icon = "✅" if status == "success" else "❌"
            status_text = "Connected" if status == "success" else "Connection Failed"
            
            html_content = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5; }}
                    .container {{ max-width: 600px; margin: 40px auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
                    .header {{ background: {status_color}; color: white; padding: 30px; text-align: center; }}
                    .header h1 {{ margin: 0; font-size: 24px; font-weight: 600; color: white; }}
                    .content {{ padding: 35px; }}
                    .status-badge {{ display: inline-block; background: {status_color}; color: white; padding: 8px 16px; border-radius: 20px; font-size: 14px; font-weight: 600; margin-bottom: 20px; }}
                    .info-box {{ background: #f8f9fa; padding: 15px; border-left: 4px solid {status_color}; border-radius: 4px; margin-top: 20px; }}
                    .footer {{ padding: 20px 35px; background: #f8f9fa; border-top: 1px solid #e0e0e0; text-align: center; font-size: 12px; color: #666; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>{status_icon} Telegram Monitor Health Check</h1>
                    </div>
                    <div class="content">
                        <span class="status-badge">{status_text}</span>
                        <h3>Status Report</h3>
                        <div class="info-box">
                            <strong>Message:</strong><br>
                            {message}
                        </div>
                        <div class="info-box">
                            <strong>Timestamp:</strong><br>
                            {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                        </div>
                    </div>
                    <div class="footer">
                        <div>Napas OSINT Monitor</div>
                    </div>
                </div>
            </body>
            </html>
            """
            
            to_emails = [email.strip() for email in HC_EMAIL_TO.split(',')]
            EmailService.send_email(
                f"[Health Check] Telegram Monitor - {status_text}",
                html_content,
                to_emails
            )
            
            print(f"   📧 Health check email sent")
        except Exception as e:
            print(f"   ⚠️  Could not send health check email: {e}")