import os
import asyncio
from telethon import TelegramClient
from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')

async def login():
    """Login to Telegram and save session"""
    print("="*60)
    print("🔐 Telegram Login Setup")
    print("="*60)
    print()
    
    # Create sessions directory if it doesn't exist
    os.makedirs('sessions', exist_ok=True)
    
    # Create client
    client = TelegramClient('sessions/monitor_session', API_ID, API_HASH)
    
    print("📱 Connecting to Telegram...")
    print()
    
    # Start the client (this will prompt for phone/code/password)
    await client.start()
    
    # Get user info
    me = await client.get_me()
    
    print()
    print("="*60)
    print(f"✅ Successfully logged in!")
    print(f"   Name: {me.first_name} {me.last_name or ''}")
    print(f"   Phone: {me.phone}")
    print(f"   Username: @{me.username}" if me.username else "")
    print()
    print(f"📁 Session saved to: sessions/monitor_session.session")
    print()
    print("🚀 You can now run: python3 multi_bot_telegram.py")
    print("="*60)
    
    await client.disconnect()

if __name__ == '__main__':
    try:
        asyncio.run(login())
    except KeyboardInterrupt:
        print("\n\n❌ Login cancelled by user")
    except Exception as e:
        print(f"\n\n❌ Error during login: {e}")
        import traceback
        traceback.print_exc()