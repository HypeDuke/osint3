"""
Main Monitor Script
Orchestrates the search and listening workflow
"""
import os
import json
import asyncio
import pickle
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError, 
    ServerError, 
    TimedOutError
)
from dotenv import load_dotenv

# Import custom modules
from email_service import EmailService
from channel_search import ChannelSearcher
from realtime_listener import RealtimeListener

load_dotenv()

# Telegram credentials
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')

# Connection settings
MAX_RETRIES = int(os.getenv('MAX_RETRIES', '5'))
RETRY_DELAY = int(os.getenv('RETRY_DELAY', '10'))
RECONNECT_DELAY = int(os.getenv('RECONNECT_DELAY', '30'))
PING_INTERVAL = int(os.getenv('PING_INTERVAL', '60'))

# Files
STATE_FILE = 'sessions/monitor_state.pkl'
SESSION_FILE = 'sessions/monitor_session.session'


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


def check_session_exists():
    """Check if session file exists"""
    if not os.path.exists(SESSION_FILE):
        print("="*60)
        print("❌ ERROR: Session file not found!")
        print("="*60)
        print()
        print("You need to login first. Run:")
        print("   python3 login_telegram.py")
        print()
        print("="*60)
        return False
    return True


class TelegramMonitor:
    """Main monitor orchestrator"""
    
    def __init__(self):
        self.client = TelegramClient(
            'sessions/monitor_session', 
            API_ID, 
            API_HASH,
            connection_retries=MAX_RETRIES,
            retry_delay=RETRY_DELAY,
            auto_reconnect=True,
            timeout=30,
            request_retries=3
        )
        
        self.state = self._load_state()
        self.channels_config = load_channels_config()
        self.is_connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.ping_task = None
        
        # Initialize modules
        self.searcher = None
        self.listener = None
    
    def _load_state(self):
        """Load state from file"""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'rb') as f:
                    return pickle.load(f)
            except:
                pass
        return {
            'initialized_channels': [],
            'last_message_ids': {}
        }
    
    def save_state(self):
        """Save state to file"""
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            with open(STATE_FILE, 'wb') as f:
                pickle.dump(self.state, f)
        except Exception as e:
            print(f"⚠️  Error saving state: {e}")
    
    async def keep_alive_ping(self):
        """Send periodic pings to keep connection alive"""
        while self.is_connected:
            try:
                await asyncio.sleep(PING_INTERVAL)
                if self.is_connected:
                    await self.client.get_me()
                    print(f"   💓 Keep-alive ping sent")
            except Exception as e:
                print(f"   ⚠️  Keep-alive ping failed: {e}")
                break
    
    async def connect_with_retry(self):
        """Connect to Telegram with retry logic"""
        for attempt in range(1, self.max_reconnect_attempts + 1):
            try:
                print(f"🔌 Connection attempt {attempt}/{self.max_reconnect_attempts}...")
                
                if not self.client.is_connected():
                    await self.client.connect()
                
                if not await self.client.is_user_authorized():
                    print("   ❌ Session is not authorized!")
                    print("   Please run: python3 login_telegram.py")
                    return False
                
                me = await self.client.get_me()
                
                if me is None:
                    raise Exception("Failed to get user info")
                
                self.is_connected = True
                self.reconnect_attempts = 0
                
                print(f"✅ Connected to Telegram as {me.first_name}")
                
                # Start keep-alive ping
                if self.ping_task:
                    self.ping_task.cancel()
                self.ping_task = asyncio.create_task(self.keep_alive_ping())
                
                # Send health check email
                EmailService.send_health_check_email(
                    status="success", 
                    message=f"Successfully connected as {me.first_name} (Attempt {attempt})"
                )
                
                return True
                
            except (TimedOutError, ServerError, OSError) as e:
                print(f"   ⚠️  Connection error on attempt {attempt}: {e}")
            except Exception as e:
                print(f"   ❌ Unexpected error on attempt {attempt}: {e}")
                import traceback
                traceback.print_exc()
            
            if attempt < self.max_reconnect_attempts:
                delay = RECONNECT_DELAY * attempt
                print(f"   ⏳ Waiting {delay}s before retry...")
                await asyncio.sleep(delay)
        
        # All attempts failed
        print(f"❌ Failed to connect after {self.max_reconnect_attempts} attempts")
        self.is_connected = False
        
        EmailService.send_health_check_email(
            status="failed", 
            message=f"Failed to connect after {self.max_reconnect_attempts} attempts"
        )
        
        return False
    
    async def ensure_connected(self):
        """Ensure client is connected, reconnect if necessary"""
        if not self.is_connected or not self.client.is_connected():
            print("\n⚠️  Connection lost, attempting to reconnect...")
            self.is_connected = False
            return await self.connect_with_retry()
        return True
    
    async def initialize_channels(self):
        """Run initial search on all channels"""
        print("\n" + "="*60)
        print("🚀 INITIALIZATION PHASE")
        print("="*60)
        
        self.searcher = ChannelSearcher(self.client, self.state)
        
        for config in self.channels_config:
            channel_id = await self.searcher.initial_search(
                config, 
                ensure_connected_callback=self.ensure_connected
            )
        
        self.save_state()
        
        print("\n" + "="*60)
        print("✅ INITIALIZATION COMPLETE")
        print("="*60)
    
    async def start_listening(self):
        """Start real-time message listening"""
        self.listener = RealtimeListener(
            self.client, 
            self.state, 
            self.channels_config
        )
        
        # Setup channels
        success = await self.listener.setup_channels()
        
        if not success:
            print("❌ No channels to monitor!")
            return False
        
        # Start listening
        await self.listener.start_listening(save_state_callback=self.save_state)
        
        return True
    
    async def run(self):
        """Main monitoring process"""
        while True:
            try:
                # Connect
                connected = await self.connect_with_retry()
                
                if not connected:
                    print("❌ Failed to establish connection. Retrying in 60s...")
                    await asyncio.sleep(60)
                    continue
                
                # Phase 1: Initial search
                await self.initialize_channels()
                
                # Phase 2: Real-time listening
                await self.start_listening()
                
            except KeyboardInterrupt:
                print("\n👋 Stopping monitor...")
                self.is_connected = False
                if self.ping_task:
                    self.ping_task.cancel()
                self.save_state()
                break
                
            except Exception as e:
                print(f"\n❌ Unexpected error in main loop: {e}")
                import traceback
                traceback.print_exc()
                
                self.is_connected = False
                if self.ping_task:
                    self.ping_task.cancel()
                
                print(f"⏳ Reconnecting in {RECONNECT_DELAY}s...")
                await asyncio.sleep(RECONNECT_DELAY)


async def main():
    """Entry point"""
    if not check_session_exists():
        return
    
    monitor = TelegramMonitor()
    await monitor.run()


if __name__ == '__main__':
    asyncio.run(main())