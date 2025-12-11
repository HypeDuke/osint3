import os
import json
import asyncio
from telethon import TelegramClient, events
from dotenv import load_dotenv
from email_templates_file import BotFilter

load_dotenv()

# Telegram credentials
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')

# Load channels configuration
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

class TestListener:
    """Test real-time message listening with keyword matching"""
    
    def __init__(self):
        self.client = TelegramClient('sessions/monitor_session', API_ID, API_HASH)
        self.channels_map = {}
        
    async def test_listen(self):
        """Test listening for new messages"""
        print("="*70)
        print("🧪 TEST MODE - Real-time Message Listener")
        print("="*70)
        print()
        
        # Connect
        print("🔌 Connecting to Telegram...")
        await self.client.connect()
        
        if not await self.client.is_user_authorized():
            print("❌ Not authorized! Please run: python3 login_telegram.py")
            return
        
        me = await self.client.get_me()
        print(f"✅ Connected as: {me.first_name}")
        print()
        
        # Get channels
        print("📋 Loading channels from channels.json...")
        print("-"*70)
        
        channel_ids = []
        for idx, config in enumerate(CHANNELS_CONFIG, 1):
            try:
                channel_username = config.get('username')
                channel_name = config.get('name', channel_username)
                
                entity = await self.client.get_entity(channel_username)
                channel_id = entity.id
                channel_ids.append(channel_id)
                
                self.channels_map[channel_id] = config
                
                # Show filter info
                filter_config = config.get('filter', {})
                filter_type = filter_config.get('type', 'none')
                filter_value = filter_config.get('value', [])
                
                print(f"{idx}. ✅ {channel_name}")
                print(f"   Username: @{channel_username}")
                print(f"   Channel ID: {channel_id}")
                print(f"   Filter Type: {filter_type}")
                
                if filter_type in ['contains', 'contains_all']:
                    keywords = filter_value if isinstance(filter_value, list) else [filter_value]
                    print(f"   Keywords: {', '.join(keywords)}")
                
                print()
                
            except Exception as e:
                print(f"{idx}. ❌ Error loading {config.get('username')}: {e}")
                print()
        
        if not channel_ids:
            print("❌ No channels loaded!")
            return
        
        print("="*70)
        print(f"👂 LISTENING to {len(channel_ids)} channels...")
        print("="*70)
        print("Waiting for new messages... (Press Ctrl+C to stop)")
        print("="*70)
        print()
        
        # Register event handler
        @self.client.on(events.NewMessage(chats=channel_ids))
        async def handler(event):
            await self.handle_message(event)
        
        # Keep running
        await self.client.run_until_disconnected()
    
    async def handle_message(self, event):
        """Handle incoming message"""
        try:
            channel_id = event.chat_id
            message = event.message
            
            if channel_id not in self.channels_map:
                return
            
            config = self.channels_map[channel_id]
            channel_name = config.get('name', 'Unknown')
            filter_config = config.get('filter', {})
            
            # Message info
            print("\n" + "="*70)
            print(f"📨 NEW MESSAGE RECEIVED")
            print("="*70)
            print(f"🔹 Channel: {channel_name}")
            print(f"🔹 Message ID: {message.id}")
            print(f"🔹 Date: {message.date.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"🔹 Has Text: {bool(message.text)}")
            print("-"*70)
            
            if not message.text:
                print("⚠️  No text content in this message")
                print("="*70)
                return
            
            # Show message content
            print("📝 MESSAGE CONTENT:")
            print("-"*70)
            print(message.text)
            print("-"*70)
            print()
            
            # Test filter
            filter_type = filter_config.get('type', 'none')
            filter_value = filter_config.get('value', [])
            
            print("🔍 FILTER TEST:")
            print(f"   Filter Type: {filter_type}")
            
            if filter_type in ['contains', 'contains_all']:
                keywords = filter_value if isinstance(filter_value, list) else [filter_value]
                print(f"   Keywords to match: {keywords}")
                print()
                
                # Check each keyword
                found_keywords = []
                missing_keywords = []
                
                for keyword in keywords:
                    keyword_lower = keyword.lower()
                    message_lower = message.text.lower()
                    
                    if keyword_lower in message_lower:
                        found_keywords.append(keyword)
                        print(f"   ✅ Found: '{keyword}'")
                    else:
                        missing_keywords.append(keyword)
                        print(f"   ❌ Missing: '{keyword}'")
                
                print()
                print(f"   Summary: {len(found_keywords)}/{len(keywords)} keywords found")
                print()
                
                # Apply filter
                passed = BotFilter.apply_filter(message.text, filter_config)
                
                if passed:
                    print("🎯 RESULT: ✅ MESSAGE PASSED FILTER")
                    print("   → This message WOULD be sent via email")
                else:
                    print("🎯 RESULT: ❌ MESSAGE FILTERED OUT")
                    print("   → This message would NOT be sent via email")
                    
                    if filter_type == 'contains_all':
                        print(f"   → Reason: 'contains_all' requires ALL keywords, but {len(missing_keywords)} missing")
                    elif filter_type == 'contains':
                        print(f"   → Reason: 'contains' requires at least ONE keyword, but none found")
            
            elif filter_type == 'regex':
                pattern = filter_config.get('value', '')
                print(f"   Regex Pattern: {pattern}")
                print()
                
                passed = BotFilter.apply_filter(message.text, filter_config)
                
                if passed:
                    print("🎯 RESULT: ✅ MESSAGE PASSED FILTER")
                    print("   → Regex pattern matched")
                else:
                    print("🎯 RESULT: ❌ MESSAGE FILTERED OUT")
                    print("   → Regex pattern did not match")
            
            else:
                print("   No filter configured (all messages pass)")
                print()
                print("🎯 RESULT: ✅ MESSAGE PASSED (no filter)")
            
            print("="*70)
            print()
            
        except Exception as e:
            print(f"\n❌ Error handling message: {e}")
            import traceback
            traceback.print_exc()

async def main():
    """Main test function"""
    # Check session exists
    if not os.path.exists('sessions/monitor_session.session'):
        print("="*70)
        print("❌ ERROR: Session file not found!")
        print("="*70)
        print()
        print("Please run first: python3 login_telegram.py")
        print()
        return
    
    listener = TestListener()
    
    try:
        await listener.test_listen()
    except KeyboardInterrupt:
        print("\n\n👋 Test stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await listener.client.disconnect()
        print("\n✅ Disconnected")

if __name__ == '__main__':
    asyncio.run(main())