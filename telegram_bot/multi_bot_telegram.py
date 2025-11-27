import os
import json
import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from telethon import TelegramClient
from dotenv import load_dotenv
import re

load_dotenv()

# Telegram credentials
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')

# Email credentials
EMAIL_FROM = os.getenv('EMAIL_FROM')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
EMAIL_TO = os.getenv('EMAIL_TO')
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))

# Bot configurations
BOTS_CONFIG = json.loads(os.getenv('BOTS_CONFIG', '[]'))

# Check interval (seconds)
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '300'))


class BotFilter:
    """Filter class for bot messages"""
    
    @staticmethod
    def apply_filter(message_text, filter_config):
        """Apply filter based on configuration"""
        if not filter_config:
            return True
        
        filter_type = filter_config.get('type', 'contains')
        filter_value = filter_config.get('value', '')
        
        if filter_type == 'contains':
            return filter_value.lower() in message_text.lower()
        elif filter_type == 'starts_with':
            return message_text.lower().startswith(filter_value.lower())
        elif filter_type == 'ends_with':
            return message_text.lower().endswith(filter_value.lower())
        elif filter_type == 'regex':
            return bool(re.search(filter_value, message_text, re.IGNORECASE))
        elif filter_type == 'not_contains':
            return filter_value.lower() not in message_text.lower()
        
        return True


class TelegramBotMonitor:
    def __init__(self):
        self.client = TelegramClient('sessions/monitor_session', API_ID, API_HASH)
        self.collected_data = {}
        
    async def connect(self):
        """Connect to Telegram"""
        await self.client.start()
        print("✅ Connected to Telegram")
    
    async def get_bot_messages(self, bot_username, filter_config, limit=20):
        """Get messages from a specific bot with filter"""
        try:
            messages = await self.client.get_messages(bot_username, limit=limit)
            filtered_messages = []
            
            for msg in messages:
                if msg.text:
                    if BotFilter.apply_filter(msg.text, filter_config):
                        filtered_messages.append({
                            'date': msg.date.strftime('%Y-%m-%d %H:%M:%S'),
                            'text': msg.text,
                            'id': msg.id
                        })
            
            return filtered_messages
        except Exception as e:
            print(f"❌ Error getting messages from {bot_username}: {e}")
            return []
    
    async def collect_from_all_bots(self):
        """Collect data from all configured bots"""
        print(f"\n🔍 Collecting data at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        for bot_config in BOTS_CONFIG:
            bot_username = bot_config.get('username')
            bot_name = bot_config.get('name', bot_username)
            filter_config = bot_config.get('filter')
            message_limit = bot_config.get('limit', 20)
            
            print(f"  📱 Checking {bot_name} ({bot_username})...")
            
            messages = await self.get_bot_messages(bot_username, filter_config, message_limit)
            
            if messages:
                self.collected_data[bot_name] = {
                    'username': bot_username,
                    'filter': filter_config,
                    'messages': messages,
                    'count': len(messages)
                }
                print(f"    ✅ Found {len(messages)} filtered messages")
            else:
                print(f"    ⚠️  No messages found")
    
    def format_data_for_email(self):
        """Format collected data for email"""
        if not self.collected_data:
            return None
        
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                h1 {{ color: #2c3e50; }}
                h2 {{ color: #34495e; margin-top: 30px; }}
                .bot-section {{ 
                    background-color: #f8f9fa; 
                    padding: 15px; 
                    margin: 20px 0; 
                    border-radius: 5px;
                    border-left: 4px solid #3498db;
                }}
                .message {{ 
                    background-color: white; 
                    padding: 10px; 
                    margin: 10px 0; 
                    border-radius: 3px;
                    border: 1px solid #dee2e6;
                }}
                .date {{ color: #7f8c8d; font-size: 0.9em; }}
                .filter-info {{ 
                    background-color: #e8f4f8; 
                    padding: 8px; 
                    border-radius: 3px; 
                    font-size: 0.9em;
                    margin-bottom: 10px;
                }}
            </style>
        </head>
        <body>
            <h1>🤖 Telegram Bot Monitor Report</h1>
            <p><strong>Report Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p><strong>Total Bots Monitored:</strong> {len(self.collected_data)}</p>
        """
        
        for bot_name, data in self.collected_data.items():
            filter_info = data['filter'] if data['filter'] else {'type': 'none', 'value': 'No filter'}
            
            html_content += f"""
            <div class="bot-section">
                <h2>📱 {bot_name}</h2>
                <p><strong>Username:</strong> {data['username']}</p>
                <div class="filter-info">
                    <strong>Filter:</strong> {filter_info.get('type', 'none')} 
                    {f"- '{filter_info.get('value', '')}'" if filter_info.get('value') else ''}
                </div>
                <p><strong>Messages Found:</strong> {data['count']}</p>
            """
            
            for msg in data['messages']:
                html_content += f"""
                <div class="message">
                    <div class="date">📅 {msg['date']}</div>
                    <div>{msg['text'].replace('\n', '<br>')}</div>
                </div>
                """
            
            html_content += "</div>"
        
        html_content += """
        </body>
        </html>
        """
        
        return html_content
    
    def send_email(self, html_content):
        """Send email with collected data"""
        if not html_content:
            print("⚠️  No data to send")
            return False
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"Telegram Bot Monitor Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            msg['From'] = EMAIL_FROM
            msg['To'] = EMAIL_TO
            
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(EMAIL_FROM, EMAIL_PASSWORD)
                server.send_message(msg)
            
            print(f"✅ Email sent successfully to {EMAIL_TO}")
            return True
        except Exception as e:
            print(f"❌ Error sending email: {e}")
            return False
    
    async def run_monitor(self):
        """Main monitoring loop"""
        await self.connect()
        
        while True:
            try:
                # Clear previous data
                self.collected_data = {}
                
                # Collect from all bots
                await self.collect_from_all_bots()
                
                # Format and send email
                email_content = self.format_data_for_email()
                if email_content:
                    self.send_email(email_content)
                
                # Wait before next check
                print(f"\n⏳ Waiting {CHECK_INTERVAL} seconds until next check...")
                await asyncio.sleep(CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                print("\n👋 Stopping monitor...")
                break
            except Exception as e:
                print(f"❌ Error in monitoring loop: {e}")
                await asyncio.sleep(60)


async def main():
    monitor = TelegramBotMonitor()
    await monitor.run_monitor()


if __name__ == '__main__':
    asyncio.run(main())