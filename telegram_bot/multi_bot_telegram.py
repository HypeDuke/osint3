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
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h3>🔔 New Message: {channel_name}</h3>
            <p><small>{message['date']}</small></p>
            <div style="background: #f5f5f5; padding: 15px; border-left: 3px solid #333;">
                {message['text'].replace('\n', '<br>')}
            </div>
        </body>
        </html>
        """
        return html
    
    @staticmethod
    def detailed_template(channel_name, message):
        """Detailed template for single message"""
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
                        {message['text'].replace('\n', '<br>')}
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
            html += f"""
            <div style="background: #f9f9f9; padding: 15px; margin: 15px 0; border-left: 3px solid #333;">
                <strong>#{idx}</strong> - <small>{msg['date']}</small><br><br>
                {msg['text'].replace('\n', '<br>')}
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
            html += f"""
            <div class="message">
                <div style="color:#667eea; font-weight:bold;">Message #{idx} (ID: {msg['id']})</div>
                <div style="color:#666; font-size:13px; margin:5px 0;">{msg['date']}</div>
                <div style="margin-top:10px;">{msg['text'].replace('\n', '<br>')}</div>
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
    
    def send_email(self, to_email, subject, html_content):
        """Send email"""
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = EMAIL_FROM
            msg['To'] = to_email
            
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(EMAIL_FROM, EMAIL_PASSWORD)
                server.send_message(msg)
            
            print(f"      ✅ Email sent to {to_email}")
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
            
            # Get search keyword
            search_keyword = None
            if filter_config and filter_config.get('type') in ['contains', 'regex']:
                search_keyword = filter_config.get('value')
            
            matched_messages = []
            
            if search_keyword:
                print(f"   🔎 Searching for keyword: '{search_keyword}'")
                print(f"   ⏳ This may take a while...")
                
                # Use Telegram's search function
                async for message in self.client.iter_messages(
                    entity, 
                    limit=search_limit,
                    search=search_keyword
                ):
                    if message.text:
                        # Apply additional filter
                        if BotFilter.apply_filter(message.text, filter_config):
                            matched_messages.append({
                                'date': message.date.strftime('%Y-%m-%d %H:%M:%S'),
                                'text': message.text,
                                'id': message.id
                            })
                
                print(f"   ✅ Found {len(matched_messages)} messages with keyword")
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
                email_to = config.get('email_to')
                if email_to:
                    template = config.get('template', 'clean')
                    email_subject = f"[Initial Search] {config.get('email_subject', channel_name)}"
                    
                    html_content = EmailTemplate.create_batch_email(
                        channel_name, 
                        matched_messages,
                        template
                    )
                    
                    print(f"   📧 Sending batch email with {len(matched_messages)} messages...")
                    self.send_email(email_to, email_subject, html_content)
            
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
            email_to = config.get('email_to')
            if email_to:
                email_subject = f"[New] {config.get('email_subject', channel_name)}"
                template = config.get('template', 'clean')
                
                html_content = EmailTemplate.create_email(channel_name, msg_data, template)
                self.send_email(email_to, email_subject, html_content)
            else:
                print(f"   ⚠️  No email configured")
                
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