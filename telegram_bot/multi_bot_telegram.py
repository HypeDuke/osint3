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
from email_templates_file import EmailTemplate, BotFilter

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
                
                template = config.get('template', 'breach')
                email_subject = f"[Napas Osint] {config.get('email_subject', channel_name)}"
                
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
            template = config.get('template', 'breach')
            
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