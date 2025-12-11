import os
import json
import asyncio
from telethon import TelegramClient, events
from telethon.tl.types import Channel
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
        self.me = None
        
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
        
        self.me = await self.client.get_me()
        print(f"✅ Connected as: {self.me.first_name}")
        print(f"   User ID: {self.me.id}")
        if self.me.username:
            print(f"   Username: @{self.me.username}")
        print()
        
        # Show available dialogs for reference
        print("📱 Your recent chats/channels (for reference):")
        print("-"*70)
        dialog_count = 0
        async for dialog in self.client.iter_dialogs(limit=10):
            dialog_count += 1
            dialog_type = "Channel" if isinstance(dialog.entity, Channel) else "Chat"
            print(f"   {dialog_count}. {dialog.name} ({dialog_type}, ID: {dialog.id})")
        print()
        
        # Get channels
        print("📋 Loading channels from channels.json...")
        print("-"*70)
        
        channel_ids = []
        channel_entities = []  # Store entities instead of just IDs
        for idx, config in enumerate(CHANNELS_CONFIG, 1):
            try:
                channel_username = config.get('username')
                channel_name = config.get('name', channel_username)
                
                # Clean username (remove @ if present)
                if channel_username.startswith('@'):
                    channel_username = channel_username[1:]
                
                print(f"{idx}. Checking: {channel_name}")
                print(f"   Username: @{channel_username}")
                
                # Try to get entity
                try:
                    entity = await self.client.get_entity(channel_username)
                    channel_id = entity.id
                    print(f"   ✅ Channel found - ID: {channel_id}")
                    
                    # Check if user is a member/subscriber
                    is_member = False
                    member_status = "Unknown"
                    
                    try:
                        # For channels, check if we can get permissions
                        if isinstance(entity, Channel):
                            try:
                                participant = await self.client.get_permissions(entity)
                                is_member = True
                                member_status = "Member/Subscriber"
                                print(f"   ✅ Membership: {member_status}")
                            except Exception as perm_error:
                                # If we can't get permissions, we might not be a member
                                # But we could still receive messages if it's a public channel
                                print(f"   ⚠️  Membership status unclear: {str(perm_error)[:50]}")
                                # Try to get recent messages as a test
                                try:
                                    messages = await self.client.get_messages(entity, limit=1)
                                    if messages:
                                        is_member = True
                                        member_status = "Can access (likely subscribed)"
                                        print(f"   ✅ Access verified: Can read messages")
                                    else:
                                        print(f"   ⚠️  No messages available to verify access")
                                        is_member = True  # Assume we can listen
                                except Exception as msg_error:
                                    print(f"   ❌ Cannot access messages: {str(msg_error)[:50]}")
                                    print(f"   ⚠️  You may NOT be subscribed to this channel!")
                                    print(f"   → Please join the channel manually first")
                        else:
                            is_member = True
                            member_status = "Chat/Group"
                            print(f"   ✅ Access: {member_status}")
                    
                    except Exception as check_error:
                        print(f"   ⚠️  Could not verify membership: {str(check_error)[:50]}")
                        is_member = True  # Try anyway
                    
                    if is_member:
                        channel_ids.append(channel_id)
                        channel_entities.append(entity)  # Store the entity
                        
                        # Store in map with BOTH ID formats (positive and with -100 prefix)
                        self.channels_map[channel_id] = config
                        # Also store with the -100 prefix format that events use
                        event_id = -1000000000000 - channel_id
                        self.channels_map[event_id] = config
                        
                        print(f"   📊 Stored with IDs: {channel_id} and {event_id}")
                        
                        # Show filter info
                        filter_config = config.get('filter', {})
                        filter_type = filter_config.get('type', 'none')
                        filter_value = filter_config.get('value', [])
                        
                        print(f"   📊 Filter Type: {filter_type}")
                        
                        if filter_type in ['contains', 'contains_all']:
                            keywords = filter_value if isinstance(filter_value, list) else [filter_value]
                            print(f"   🔑 Keywords: {', '.join(keywords)}")
                        elif filter_type == 'regex':
                            print(f"   🔍 Pattern: {filter_value}")
                        
                        print(f"   ✅ WILL LISTEN to this channel")
                    else:
                        print(f"   ❌ SKIPPING - Not subscribed/no access")
                
                except Exception as entity_error:
                    print(f"   ❌ Error accessing channel: {entity_error}")
                    print(f"   → Make sure the username is correct")
                    print(f"   → Make sure you're subscribed to the channel")
                
                print()
                
            except Exception as e:
                print(f"{idx}. ❌ Error loading {config.get('username')}: {e}")
                print()
        
        if not channel_ids:
            print("="*70)
            print("❌ No valid channels loaded!")
            print("="*70)
            print()
            print("💡 Troubleshooting tips:")
            print("   1. Make sure you're subscribed to all channels in channels.json")
            print("   2. Check that channel usernames are correct")
            print("   3. Try accessing the channels manually in Telegram first")
            print("   4. For private channels, ensure you have access")
            print()
            return
        
        print("="*70)
        print(f"👂 LISTENING to {len(channel_entities)} channels...")
        print("="*70)
        print("Waiting for new messages... (Press Ctrl+C to stop)")
        print()
        print("💡 TIP: Only NEW messages (sent after starting this script) will appear")
        print("💡 TIP: Try sending a test message to one of the channels")
        print("="*70)
        print()
        
        # Register event handler - USE ENTITIES instead of IDs
        @self.client.on(events.NewMessage(chats=channel_entities))
        async def handler(event):
            await self.handle_message(event)
        
        # Also listen to ALL messages for debugging (optional)
        @self.client.on(events.NewMessage())
        async def debug_handler(event):
            # Only log if it's NOT from our monitored channels
            if event.chat_id not in self.channels_map:
                chat_name = "Unknown"
                try:
                    chat = await event.get_chat()
                    chat_name = getattr(chat, 'title', getattr(chat, 'first_name', 'Unknown'))
                except:
                    pass
                print(f"🔔 Debug: Message from unmonitored chat: {chat_name} (ID: {event.chat_id})")
        
        # Keep running
        await self.client.run_until_disconnected()
    
    async def handle_message(self, event):
        """Handle incoming message"""
        try:
            channel_id = event.chat_id
            message = event.message
            
            if channel_id not in self.channels_map:
                print(f"⚠️  Message from unmonitored channel ID: {channel_id}")
                return
            
            config = self.channels_map[channel_id]
            channel_name = config.get('name', 'Unknown')
            filter_config = config.get('filter', {})
            
            # Check if message is from self
            is_own_message = message.sender_id == self.me.id
            
            # Message info
            print("\n" + "="*70)
            print(f"📨 NEW MESSAGE RECEIVED")
            print("="*70)
            print(f"🔹 Channel: {channel_name}")
            print(f"🔹 Message ID: {message.id}")
            print(f"🔹 Date: {message.date.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"🔹 Sender ID: {message.sender_id}")
            if is_own_message:
                print(f"🔹 ⚠️  This is YOUR message")
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