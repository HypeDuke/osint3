import os
import json
import asyncio
import smtplib
import pickle
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from telethon import TelegramClient, events
from dotenv import load_dotenv
import re

load_dotenv()

# Telegram credentials
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')


# Email credentials
EMAIL_FROM = os.getenv('EMAIL_FROM')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
EMAIL_TO = os.getenv('EMAIL_TO')  # Can be comma-separated for multiple recipients
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '465'))

# Load channels configuration from JSON file
def load_channels_config():
    """Load channels configuration from channels.json"""
    try:
        with open('channels.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ Error: channels.json not found!")
        return []
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing channels.json: {e}")
        return []

CHANNELS_CONFIG = load_channels_config()

# State file
STATE_FILE = 'sessions/monitor_state.pkl'


class BotFilter:
    """Filter class for messages"""
    
    @staticmethod
    def apply_filter(message_text, filter_config):
        """Apply filter based on configuration"""
        if not filter_config:
            return True
        
        filter_type = filter_config.get('type', 'contains')
        filter_value = filter_config.get('value', '')
        
        if not filter_value:
            return True
        
        # Support multiple keywords (list or comma-separated string)
        keywords = []
        if isinstance(filter_value, list):
            keywords = filter_value
        elif isinstance(filter_value, str):
            keywords = [k.strip() for k in filter_value.split(',')]
        
        if filter_type == 'contains':
            # Match if ANY keyword is found
            return any(keyword.lower() in message_text.lower() for keyword in keywords)
        elif filter_type == 'contains_all':
            # Match if ALL keywords are found
            return all(keyword.lower() in message_text.lower() for keyword in keywords)
        elif filter_type == 'starts_with':
            return any(message_text.lower().startswith(keyword.lower()) for keyword in keywords)
        elif filter_type == 'ends_with':
            return any(message_text.lower().endswith(keyword.lower()) for keyword in keywords)
        elif filter_type == 'regex':
            return bool(re.search(filter_value, message_text, re.IGNORECASE))
        elif filter_type == 'not_contains':
            # Match if NONE of the keywords are found
            return not any(keyword.lower() in message_text.lower() for keyword in keywords)
        
        return True

    
class EmailTemplate:
    """Email templates"""
    
    @staticmethod
    def create_email(channel_name, message, template='clean'):
        """Create email for a message"""
        if template == 'clean':
            return EmailTemplate.clean_template(channel_name, message)
        elif template == 'detailed':
            return EmailTemplate.detailed_template(channel_name, message)
        else:
            return EmailTemplate.minimal_template(channel_name, message)
    
    @staticmethod
    def create_batch_email(channel_name, messages, template='clean'):
        """Create email for multiple messages (initial search)"""
        if template == 'clean':
            return EmailTemplate.clean_batch_template(channel_name, messages)
        elif template == 'detailed':
            return EmailTemplate.detailed_batch_template(channel_name, messages)
        else:
            return EmailTemplate.minimal_batch_template(channel_name, messages)
    
    @staticmethod
    def minimal_template(channel_name, message):
        """Minimal template for single message"""
        
        formated_text = message['text'].replace('\n', '<br>')
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h3>🔔 New Message: {channel_name}</h3>
            <p><small>{message['date']}</small></p>
            <div style="background: #f5f5f5; padding: 15px; border-left: 3px solid #333;">
                {formated_text}
            </div>
        </body>
        </html>
        """
        return html
    
    @staticmethod
    def detailed_template(channel_name, message):
        """Detailed template for single message"""
        # Parse structured data if present
        text = message['text']
        title = content = None
        
        # Try to extract structured fields
        if '"Title":' in text or '"CVE ID":' in text:
            import json
            try:
                # Extract JSON part (before the ** markers)
                json_part = text.split('**')[0].strip()
                data = json.loads(json_part)
                title = data.get('Title', '')
                content = data.get('Content', '')
                
                # Remove the "Visit the link..." sentence from content
                if content:
                    content = re.sub(r'Visit the link.*?\.\.\.', '', content, flags=re.IGNORECASE | re.DOTALL).strip()
            except:
                pass
        
        # If structured data found, use formal CVE report template
        if title or content:
            # Format content with line breaks
            formatted_content = content.replace('\n', '<br>') if content else 'N/A'
            
            html = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5; }}
                    .container {{ max-width: 700px; margin: 40px auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
                    .header {{ background: linear-gradient(135deg, #c62828 0%, #e53935 100%); color: white; padding: 30px; text-align: center; }}
                    .header h1 {{ margin: 0; font-size: 24px; font-weight: 600; }}
                    .header p {{ margin: 5px 0 0 0; opacity: 0.9; font-size: 14px; }}
                    .content {{ padding: 35px; }}
                    .title-section {{ background: #fff3e0; border-left: 4px solid #e53935; padding: 20px; margin-bottom: 30px; border-radius: 4px; }}
                    .title-label {{ font-size: 11px; text-transform: uppercase; color: #c62828; font-weight: 600; letter-spacing: 0.5px; margin-bottom: 10px; }}
                    .title-value {{ font-size: 18px; color: #333; font-weight: 600; line-height: 1.4; }}
                    .field {{ margin-bottom: 25px; }}
                    .field-label {{ font-size: 11px; text-transform: uppercase; color: #666; font-weight: 600; letter-spacing: 0.5px; margin-bottom: 8px; }}
                    .field-value {{ font-size: 14px; color: #333; line-height: 1.8; padding: 15px; background: #f8f9fa; border-left: 3px solid #e53935; border-radius: 4px; }}
                    .footer {{ padding: 20px 35px; background: #f8f9fa; border-top: 1px solid #e0e0e0; text-align: center; font-size: 12px; color: #666; }}
                    .timestamp {{ color: #999; font-size: 11px; }}
                    .cve-badge {{ display: inline-block; background: #c62828; color: white; padding: 4px 12px; border-radius: 12px; font-size: 11px; font-weight: 600; margin-bottom: 10px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>⚠️ CVE Security Alert</h1>
                        <p>{channel_name}</p>
                    </div>
                    <div class="content">
                        <div class="title-section">
                            <span class="cve-badge">VULNERABILITY ALERT</span>
                            <div class="title-label">Vulnerability Title</div>
                            <div class="title-value">{title if title else 'N/A'}</div>
                        </div>
                        <div class="field">
                            <div class="field-label">Details & Description</div>
                            <div class="field-value">{formatted_content if formatted_content else 'N/A'}</div>
                        </div>
                    </div>
                    <div class="footer">
                        <div class="timestamp">Report generated: {message['date']}</div>
                        <div style="margin-top: 8px;">Message ID: {message['id']}</div>
                    </div>
                </div>
            </body>
            </html>
            """
        else:
            # Fallback to original detailed template
            formated_text = message['text'].replace('\n', '<br>')
            html = f"""
            <html>
            <head>
                <style>
                    body {{ margin: 0; padding: 0; font-family: Arial, sans-serif; }}
                    .container {{ max-width: 600px; margin: 20px auto; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
                    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; }}
                    .content {{ padding: 20px; background: white; }}
                    .message {{ background: #f8f9fa; padding: 15px; border-radius: 5px; border-left: 4px solid #667eea; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2 style="margin:0;">🔔 New Message</h2>
                        <p style="margin:5px 0 0 0; opacity:0.9;">{channel_name}</p>
                    </div>
                    <div class="content">
                        <div class="message">
                            <small style="color:#666;">{message['date']} (ID: {message['id']})</small><br><br>
                            {formated_text}
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
        return html
    
    @staticmethod
    def clean_template(channel_name, message):
        """Clean template for single message"""
        # Parse structured data if present
        text = message['text']
        source = content = detection_date = None
        
        # Try to extract structured fields
        if '"Source":' in text or '"source":' in text.lower():
            import json
            try:
                # Try different extraction methods
                # Method 1: Direct JSON parse
                try:
                    data = json.loads(text)
                    source = data.get('Source', data.get('source', ''))
                    content = data.get('Content', data.get('content', ''))
                    detection_date = data.get('Detection Date', data.get('detection_date', ''))
                except:
                    # Method 2: Extract JSON part before ** markers or newlines
                    json_part = text
                    if '**' in text:
                        json_part = text.split('**')[0].strip()
                    elif '\n\n' in text:
                        # Sometimes JSON is in first paragraph
                        json_part = text.split('\n\n')[0].strip()
                    
                    # Try to find JSON object pattern
                    import re
                    json_match = re.search(r'\{[^}]+\}', json_part, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0)
                        data = json.loads(json_str)
                        source = data.get('Source', data.get('source', ''))
                        content = data.get('Content', data.get('content', ''))
                        detection_date = data.get('Detection Date', data.get('detection_date', ''))
            except Exception as e:
                print(f"   ⚠️  JSON parse error: {e}")
                pass
        
        # If structured data found, use formal report template
        if source or content or detection_date:
            html = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5; }}
                    .container {{ max-width: 650px; margin: 40px auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
                    .header {{ background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: white; padding: 30px; text-align: center; }}
                    .header h1 {{ margin: 0; font-size: 24px; font-weight: 600; }}
                    .header p {{ margin: 5px 0 0 0; opacity: 0.9; font-size: 14px; }}
                    .content {{ padding: 35px; }}
                    .field {{ margin-bottom: 25px; }}
                    .field-label {{ font-size: 11px; text-transform: uppercase; color: #666; font-weight: 600; letter-spacing: 0.5px; margin-bottom: 8px; }}
                    .field-value {{ font-size: 15px; color: #333; line-height: 1.6; padding: 12px; background: #f8f9fa; border-left: 3px solid #2a5298; border-radius: 4px; }}
                    .footer {{ padding: 20px 35px; background: #f8f9fa; border-top: 1px solid #e0e0e0; text-align: center; font-size: 12px; color: #666; }}
                    .timestamp {{ color: #999; font-size: 11px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🔒 Security Alert</h1>
                        <p>{channel_name}</p>
                    </div>
                    <div class="content">
                        <div class="field">
                            <div class="field-label">Source</div>
                            <div class="field-value">{source if source else 'N/A'}</div>
                        </div>
                        <div class="field">
                            <div class="field-label">Content Description</div>
                            <div class="field-value">{content if content else 'N/A'}</div>
                        </div>
                        <div class="field">
                            <div class="field-label">Detection Date</div>
                            <div class="field-value">{detection_date if detection_date else 'N/A'}</div>
                        </div>
                    </div>
                    <div class="footer">
                        <div class="timestamp">Report generated: {message['date']}</div>
                        <div style="margin-top: 8px;">Message ID: {message['id']}</div>
                    </div>
                </div>
            </body>
            </html>
            """
        else:
            # Fallback to original clean template for non-structured data
            html = f"""
            <html>
            <body style="font-family: 'Courier New', monospace; margin: 0; padding: 40px; background: white; color: #000;">
                <div style="border-bottom: 1px solid #000; padding-bottom: 10px; margin-bottom: 20px;">
                    <strong>🔔 NEW: {channel_name}</strong><br>
                    <small>{message['date']}</small>
                </div>
                <div style="white-space: pre-wrap; line-height: 1.6;">
{message['text']}
                </div>
            </body>
            </html>
            """
        return html
    
    @staticmethod
    def minimal_batch_template(channel_name, messages):
        """Minimal batch template"""
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>📊 Initial Search Results: {channel_name}</h2>
            <p><strong>Found {len(messages)} messages</strong></p>
            <p><small>Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</small></p>
            <hr>
        """
        
        for idx, msg in enumerate(messages, 1):
            formated_text = msg['text'].replace('\n', '<br>')
            html += f"""
            <div style="background: #f9f9f9; padding: 15px; margin: 15px 0; border-left: 3px solid #333;">
                <strong>#{idx}</strong> - <small>{msg['date']}</small><br><br>
                {formated_text}
            </div>
            """
        
        html += """
        </body>
        </html>
        """
        return html
    
    @staticmethod
    def detailed_batch_template(channel_name, messages):
        """Detailed batch template"""
        # Check if messages contain CVE structured data
        has_cve_data = False
        if messages and ('"Title":' in messages[0]['text'] or '"CVE ID":' in messages[0]['text']):
            has_cve_data = True
        
        if has_cve_data:
            html = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5; }}
                    .container {{ max-width: 850px; margin: 40px auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
                    .header {{ background: linear-gradient(135deg, #c62828 0%, #e53935 100%); color: white; padding: 35px; text-align: center; }}
                    .header h1 {{ margin: 0; font-size: 28px; font-weight: 600; }}
                    .header p {{ margin: 8px 0 0 0; opacity: 0.9; font-size: 15px; }}
                    .summary {{ padding: 25px 35px; background: #fff3e0; border-bottom: 1px solid #e0e0e0; }}
                    .summary-item {{ display: inline-block; margin-right: 30px; }}
                    .summary-label {{ font-size: 11px; text-transform: uppercase; color: #c62828; font-weight: 600; }}
                    .summary-value {{ font-size: 24px; color: #c62828; font-weight: 600; }}
                    .content {{ padding: 35px; }}
                    .cve-item {{ background: white; border: 1px solid #e0e0e0; border-radius: 6px; margin-bottom: 25px; overflow: hidden; }}
                    .cve-header {{ background: #f8f9fa; padding: 15px 20px; border-bottom: 1px solid #e0e0e0; }}
                    .cve-number {{ font-weight: 600; color: #c62828; }}
                    .cve-badge {{ display: inline-block; background: #c62828; color: white; padding: 3px 10px; border-radius: 10px; font-size: 10px; font-weight: 600; margin-left: 10px; }}
                    .cve-body {{ padding: 25px; }}
                    .title-section {{ background: #fff3e0; border-left: 4px solid #e53935; padding: 15px; margin-bottom: 20px; border-radius: 4px; }}
                    .title-value {{ font-size: 16px; color: #333; font-weight: 600; line-height: 1.5; }}
                    .field {{ margin-bottom: 15px; }}
                    .field-label {{ font-size: 11px; text-transform: uppercase; color: #666; font-weight: 600; letter-spacing: 0.5px; margin-bottom: 8px; }}
                    .field-value {{ font-size: 14px; color: #333; line-height: 1.7; padding: 12px; background: #f8f9fa; border-left: 3px solid #e53935; border-radius: 3px; }}
                    .footer {{ padding: 20px 35px; background: #f8f9fa; border-top: 1px solid #e0e0e0; text-align: center; font-size: 12px; color: #666; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>⚠️ CVE Security Report</h1>
                        <p>{channel_name}</p>
                    </div>
                    <div class="summary">
                        <div class="summary-item">
                            <div class="summary-label">Total Vulnerabilities</div>
                            <div class="summary-value">{len(messages)}</div>
                        </div>
                        <div class="summary-item">
                            <div class="summary-label">Report Date</div>
                            <div class="summary-value" style="font-size: 16px;">{datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
                        </div>
                    </div>
                    <div class="content">
            """
            
            for idx, msg in enumerate(messages, 1):
                # Parse structured data
                text = msg['text']
                title = content = None
                
                try:
                    json_part = text.split('**')[0].strip()
                    data = json.loads(json_part)
                    title = data.get('Title', 'N/A')
                    content = data.get('Content', 'N/A')
                    
                    # Remove the "Visit the link..." sentence
                    if content:
                        content = re.sub(r'Visit the link.*?\.\.\.', '', content, flags=re.IGNORECASE | re.DOTALL).strip()
                    
                    formatted_content = content.replace('\n', '<br>')
                except:
                    title = 'N/A'
                    formatted_content = 'N/A'
                
                html += f"""
                        <div class="cve-item">
                            <div class="cve-header">
                                <span class="cve-number">CVE #{idx}</span>
                                <span class="cve-badge">VULNERABILITY</span>
                                <span style="float: right; color: #999; font-size: 12px;">ID: {msg['id']}</span>
                            </div>
                            <div class="cve-body">
                                <div class="title-section">
                                    <div class="title-value">{title}</div>
                                </div>
                                <div class="field">
                                    <div class="field-label">Details & Description</div>
                                    <div class="field-value">{formatted_content}</div>
                                </div>
                            </div>
                        </div>
                """
            
            html += f"""
                    </div>
                    <div class="footer">
                        <div>Initial search completed on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
                        <div style="margin-top: 5px; color: #999;">This is an automated CVE vulnerability report</div>
                    </div>
                </div>
            </body>
            </html>
            """
        else:
            # Fallback to original template
            html = f"""
            <html>
            <head>
                <style>
                    body {{ margin: 0; padding: 0; font-family: Arial, sans-serif; background: #f4f4f4; }}
                    .container {{ max-width: 800px; margin: 20px auto; background: white; }}
                    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; }}
                    .content {{ padding: 20px; }}
                    .message {{ background: #f8f9fa; padding: 20px; margin: 15px 0; border-radius: 8px; border-left: 4px solid #667eea; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>📊 Initial Search Results</h1>
                        <p style="margin:5px 0; opacity:0.9;">{channel_name}</p>
                        <p style="margin:5px 0; opacity:0.9;">Found {len(messages)} messages</p>
                        <p style="margin:5px 0; opacity:0.9; font-size:14px;">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    </div>
                    <div class="content">
            """
            
            for idx, msg in enumerate(messages, 1):
                formated_text = msg['text'].replace('\n', '<br>')
                html += f"""
                <div class="message">
                    <div style="color:#667eea; font-weight:bold;">Message #{idx} (ID: {msg['id']})</div>
                    <div style="color:#666; font-size:13px; margin:5px 0;">{msg['date']}</div>
                    <div style="margin-top:10px;">{formated_text}</div>
                </div>
                """
            
            html += """
                    </div>
                </div>
            </body>
            </html>
            """
        
        return html
    
    @staticmethod
    def clean_batch_template(channel_name, messages):
        """Clean batch template"""
        # Check if messages contain structured data
        has_structured_data = False
        if messages and '"Source":' in messages[0]['text']:
            has_structured_data = True
        
        if has_structured_data:
            html = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5; }}
                    .container {{ max-width: 800px; margin: 40px auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
                    .header {{ background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: white; padding: 35px; text-align: center; }}
                    .header h1 {{ margin: 0; font-size: 28px; font-weight: 600; }}
                    .header p {{ margin: 8px 0 0 0; opacity: 0.9; font-size: 15px; }}
                    .summary {{ padding: 25px 35px; background: #f8f9fa; border-bottom: 1px solid #e0e0e0; }}
                    .summary-item {{ display: inline-block; margin-right: 30px; }}
                    .summary-label {{ font-size: 11px; text-transform: uppercase; color: #666; font-weight: 600; }}
                    .summary-value {{ font-size: 24px; color: #2a5298; font-weight: 600; }}
                    .content {{ padding: 35px; }}
                    .alert-item {{ background: white; border: 1px solid #e0e0e0; border-radius: 6px; margin-bottom: 20px; overflow: hidden; }}
                    .alert-header {{ background: #f8f9fa; padding: 15px 20px; border-bottom: 1px solid #e0e0e0; }}
                    .alert-number {{ font-weight: 600; color: #2a5298; }}
                    .alert-body {{ padding: 20px; }}
                    .field {{ margin-bottom: 15px; }}
                    .field-label {{ font-size: 11px; text-transform: uppercase; color: #666; font-weight: 600; letter-spacing: 0.5px; margin-bottom: 5px; }}
                    .field-value {{ font-size: 14px; color: #333; line-height: 1.5; padding: 10px; background: #f8f9fa; border-left: 3px solid #2a5298; border-radius: 3px; }}
                    .footer {{ padding: 20px 35px; background: #f8f9fa; border-top: 1px solid #e0e0e0; text-align: center; font-size: 12px; color: #666; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🔒 Security Alert Report</h1>
                        <p>{channel_name}</p>
                    </div>
                    <div class="summary">
                        <div class="summary-item">
                            <div class="summary-label">Total Alerts</div>
                            <div class="summary-value">{len(messages)}</div>
                        </div>
                        <div class="summary-item">
                            <div class="summary-label">Report Date</div>
                            <div class="summary-value" style="font-size: 16px;">{datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
                        </div>
                    </div>
                    <div class="content">
            """
            
            for idx, msg in enumerate(messages, 1):
                # Parse structured data
                text = msg['text']
                source = content = detection_date = None
                
                try:
                    # Try different parsing methods
                    try:
                        data = json.loads(text)
                        source = data.get('Source', data.get('source', 'N/A'))
                        content = data.get('Content', data.get('content', 'N/A'))
                        detection_date = data.get('Detection Date', data.get('detection_date', 'N/A'))
                    except:
                        json_part = text
                        if '**' in text:
                            json_part = text.split('**')[0].strip()
                        elif '\n\n' in text:
                            json_part = text.split('\n\n')[0].strip()
                        
                        import re
                        json_match = re.search(r'\{[^}]+\}', json_part, re.DOTALL)
                        if json_match:
                            json_str = json_match.group(0)
                            data = json.loads(json_str)
                            source = data.get('Source', data.get('source', 'N/A'))
                            content = data.get('Content', data.get('content', 'N/A'))
                            detection_date = data.get('Detection Date', data.get('detection_date', 'N/A'))
                except:
                    source = content = detection_date = 'N/A'
                
                html += f"""
                        <div class="alert-item">
                            <div class="alert-header">
                                <span class="alert-number">Alert #{idx}</span>
                                <span style="float: right; color: #999; font-size: 12px;">ID: {msg['id']}</span>
                            </div>
                            <div class="alert-body">
                                <div class="field">
                                    <div class="field-label">Source</div>
                                    <div class="field-value">{source}</div>
                                </div>
                                <div class="field">
                                    <div class="field-label">Content Description</div>
                                    <div class="field-value">{content}</div>
                                </div>
                                <div class="field">
                                    <div class="field-label">Detection Date</div>
                                    <div class="field-value">{detection_date}</div>
                                </div>
                            </div>
                        </div>
                """
            
            html += f"""
                    </div>
                    <div class="footer">
                        <div>Initial search completed on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
                        <div style="margin-top: 5px; color: #999;">This is an automated security report</div>
                    </div>
                </div>
            </body>
            </html>
            """
        else:
            # Fallback to original template
            html = f"""
            <html>
            <body style="font-family: 'Courier New', monospace; margin: 0; padding: 40px; background: white; color: #000;">
                <div style="border-bottom: 2px solid #000; padding-bottom: 10px; margin-bottom: 30px;">
                    <strong>INITIAL SEARCH RESULTS</strong><br>
                    <strong>{channel_name}</strong><br>
                    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
                    Messages found: {len(messages)}
                </div>
            """
            
            for idx, msg in enumerate(messages, 1):
                html += f"""
                <div style="border-bottom: 1px solid #ddd; padding: 20px 0;">
                    <div style="font-size: 11px; color: #666; margin-bottom: 10px;">
                        #{idx} - {msg['date']} (ID: {msg['id']})
                    </div>
                    <div style="white-space: pre-wrap; line-height: 1.6;">
{msg['text']}
                    </div>
                </div>
                """
            
            html += """
            </body>
            </html>
            """
        
        return html


class SearchAndListenMonitor:
    """Monitor that searches history first, then listens for new messages"""
    
    def __init__(self):
        self.client = TelegramClient('sessions/monitor_session', API_ID, API_HASH)
        self.state = self.load_state()
        self.channels_map = {}
        
    def load_state(self):
        """Load state from file"""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'rb') as f:
                    return pickle.load(f)
            except:
                pass
        return {
            'initialized_channels': [],  # List of channel IDs already searched
            'last_message_ids': {}       # Last message ID per channel
        }
    
    def save_state(self):
        """Save state to file"""
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            with open(STATE_FILE, 'wb') as f:
                pickle.dump(self.state, f)
        except Exception as e:
            print(f"⚠️  Error saving state: {e}")
    
    async def connect(self):
        """Connect to Telegram"""
        await self.client.start()
        me = await self.client.get_me()
        print(f"✅ Connected to Telegram as {me.first_name}")
    
    def send_email(self, subject, html_content):
        """Send email"""
        if not EMAIL_FROM or not EMAIL_PASSWORD or not EMAIL_TO:
            print("[!] Missing EMAIL_FROM, EMAIL_PASSWORD or EMAIL_TO in environment")
            return False
        
        try:
            # Parse multiple emails if comma-separated
            to_emails = [email.strip() for email in EMAIL_TO.split(',')]
            
            msg = MIMEText(html_content, "html", "utf-8")
            msg["Subject"] = subject
            msg["From"] = EMAIL_FROM
            msg["To"] = ", ".join(to_emails)
            
            print("[DEBUG] Connecting to Gmail SMTP...")
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(EMAIL_FROM, EMAIL_PASSWORD)
                server.sendmail(EMAIL_FROM, to_emails, msg.as_string())
            
            print(f"      ✅ Email sent to {', '.join(to_emails)}")
            return True
        except Exception as e:
            print(f"      ❌ Email error: {e}")
            return False
    
    async def initial_search(self, config):
        """Search all history for keyword on first run"""
        channel_username = config.get('username')
        channel_name = config.get('name', channel_username)
        filter_config = config.get('filter')
        search_limit = config.get('search_limit', 1000)
        
        print(f"\n{'='*60}")
        print(f"🔍 INITIAL SEARCH: {channel_name}")
        print(f"{'='*60}")
        
        try:
            entity = await self.client.get_entity(channel_username)
            channel_id = entity.id
            
            # Check if already initialized
            if channel_id in self.state['initialized_channels']:
                print(f"   ⏭️  Already searched, skipping initial search")
                return channel_id
            
            # Get search keywords
            search_keywords = []
            if filter_config and filter_config.get('type') in ['contains', 'contains_all']:
                filter_value = filter_config.get('value')
                if isinstance(filter_value, list):
                    search_keywords = filter_value
                elif isinstance(filter_value, str):
                    search_keywords = [k.strip() for k in filter_value.split(',')]
            
            matched_messages = []
            seen_message_ids = set()  # To avoid duplicates
            
            if search_keywords:
                print(f"   🔎 Searching for {len(search_keywords)} keywords")
                print(f"   ⏳ This may take a while...")
                
                # Search for each keyword separately
                for idx, keyword in enumerate(search_keywords, 1):
                    print(f"      [{idx}/{len(search_keywords)}] Searching: '{keyword}'...")
                    
                    try:
                        async for message in self.client.iter_messages(
                            entity, 
                            limit=search_limit,
                            search=keyword
                        ):
                            if message.text and message.id not in seen_message_ids:
                                # Apply additional filter
                                if BotFilter.apply_filter(message.text, filter_config):
                                    matched_messages.append({
                                        'date': message.date.strftime('%Y-%m-%d %H:%M:%S'),
                                        'text': message.text,
                                        'id': message.id
                                    })
                                    seen_message_ids.add(message.id)
                    except Exception as e:
                        print(f"      ⚠️  Error searching '{keyword}': {e}")
                        continue
                
                # Sort by date (newest first)
                matched_messages.sort(key=lambda x: x['date'], reverse=True)
                print(f"   ✅ Found {len(matched_messages)} unique messages")
            else:
                print(f"   ℹ️  No search keyword, getting recent messages...")
                messages = await self.client.get_messages(entity, limit=50)
                
                for message in messages:
                    if message.text and BotFilter.apply_filter(message.text, filter_config):
                        matched_messages.append({
                            'date': message.date.strftime('%Y-%m-%d %H:%M:%S'),
                            'text': message.text,
                            'id': message.id
                        })
                
                print(f"   ✅ Found {len(matched_messages)} filtered messages")
            
            # Send batch email with results
            if matched_messages:
                # Print results summary
                print(f"\n   📊 SEARCH RESULTS SUMMARY:")
                print(f"   {'='*50}")
                print(f"   Total messages found: {len(matched_messages)}")
                print(f"   {'='*50}")
                
                # Print first 3 messages as preview
                preview_count = min(3, len(matched_messages))
                for idx, msg in enumerate(matched_messages[:preview_count], 1):
                    print(f"\n   Message #{idx}:")
                    print(f"   Date: {msg['date']}")
                    print(f"   ID: {msg['id']}")
                    # Print first 200 chars of message
                    preview_text = msg['text'][:200].replace('\n', ' ')
                    print(f"   Preview: {preview_text}...")
                    print(f"   {'-'*50}")
                
                if len(matched_messages) > preview_count:
                    print(f"\n   ... and {len(matched_messages) - preview_count} more messages")
                
                print(f"\n   {'='*50}")
                
                template = config.get('template', 'clean')
                email_subject = f"[Initial Search] {config.get('email_subject', channel_name)}"
                
                html_content = EmailTemplate.create_batch_email(
                    channel_name, 
                    matched_messages,
                    template
                )
                
                print(f"   📧 Sending batch email with {len(matched_messages)} messages...")
                self.send_email(email_subject, html_content)
            
            # Get latest message ID for listening
            latest_messages = await self.client.get_messages(entity, limit=1)
            if latest_messages:
                self.state['last_message_ids'][channel_id] = latest_messages[0].id
                print(f"   📍 Latest message ID: {latest_messages[0].id}")
            
            # Mark as initialized
            self.state['initialized_channels'].append(channel_id)
            self.save_state()
            
            print(f"   ✅ Initial search completed")
            return channel_id
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def initialize_channels(self):
        """Initialize all channels"""
        print("\n" + "="*60)
        print("🚀 INITIALIZATION PHASE")
        print("="*60)
        
        for config in CHANNELS_CONFIG:
            channel_id = await self.initial_search(config)
            
            if channel_id:
                self.channels_map[channel_id] = config
        
        print("\n" + "="*60)
        print("✅ INITIALIZATION COMPLETE")
        print("="*60)
    
    async def handle_new_message(self, event):
        """Handle new message event"""
        try:
            channel_id = event.chat_id
            message = event.message
            
            # Check if we're monitoring this channel
            if channel_id not in self.channels_map:
                return
            
            config = self.channels_map[channel_id]
            channel_name = config.get('name', 'Unknown')
            filter_config = config.get('filter')
            
            # Skip if message is not newer
            if message.id <= self.state['last_message_ids'].get(channel_id, 0):
                return
            
            # Update last message ID
            self.state['last_message_ids'][channel_id] = message.id
            self.save_state()
            
            # Check if message has text
            if not message.text:
                return
            
            # Apply filter
            if not BotFilter.apply_filter(message.text, filter_config):
                print(f"   ⚠️  {channel_name}: Message filtered out (ID: {message.id})")
                return
            
            # Prepare message data
            msg_data = {
                'date': message.date.strftime('%Y-%m-%d %H:%M:%S'),
                'text': message.text,
                'id': message.id
            }
            
            print(f"\n🔔 NEW MESSAGE: {channel_name}")
            print(f"   ID: {message.id}")
            print(f"   Date: {msg_data['date']}")
            print(f"   Preview: {message.text[:100]}...")
            
            # Send email
            email_subject = f"[New] {config.get('email_subject', channel_name)}"
            template = config.get('template', 'clean')
            
            html_content = EmailTemplate.create_email(channel_name, msg_data, template)
            self.send_email(email_subject, html_content)
                
        except Exception as e:
            print(f"❌ Error handling message: {e}")
            import traceback
            traceback.print_exc()
    
    async def run_monitor(self):
        """Main monitoring process"""
        await self.connect()
        
        # Phase 1: Initial search (only on first run)
        await self.initialize_channels()
        
        # Phase 2: Real-time listening
        print("\n" + "="*60)
        print("👂 LISTENING PHASE")
        print("="*60)
        print("Listening for new messages in real-time...")
        print("Press Ctrl+C to stop")
        print("="*60 + "\n")
        
        # Get channel IDs to monitor
        channel_ids = list(self.channels_map.keys())
        
        if not channel_ids:
            print("❌ No channels to monitor!")
            return
        
        # Register event handler
        @self.client.on(events.NewMessage(chats=channel_ids))
        async def handler(event):
            await self.handle_new_message(event)
        
        # Keep running
        try:
            await self.client.run_until_disconnected()
        except KeyboardInterrupt:
            print("\n👋 Stopping monitor...")
            self.save_state()


async def main():
    monitor = SearchAndListenMonitor()
    await monitor.run_monitor()


if __name__ == '__main__':
    asyncio.run(main())