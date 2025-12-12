"""
Real-time Listener Module
Handles listening for new messages in real-time
"""
from telethon import events
from telethon.tl.types import Channel
from email_templates_file import EmailTemplate, BotFilter
from email_service import EmailService


class RealtimeListener:
    """Handles real-time message listening"""
    
    def __init__(self, client, state, channels_config):
        """
        Initialize listener
        
        Args:
            client: Telethon client instance
            state: State dictionary with last_message_ids
            channels_config: List of channel configurations
        """
        self.client = client
        self.state = state
        self.channels_config = channels_config
        self.channels_map = {}
        self.channel_entities = []
        self.me = None
    
    async def setup_channels(self):
        """
        Setup channels for listening
        
        Returns:
            bool: True if at least one channel was set up successfully
        """
        print("\n" + "="*60)
        print("📋 Setting up channels for listening...")
        print("="*60)
        
        self.me = await self.client.get_me()
        print(f"✅ Connected as: {self.me.first_name} (ID: {self.me.id})")
        print()
        
        for idx, config in enumerate(self.channels_config, 1):
            try:
                channel_username = config.get('username')
                channel_name = config.get('name', channel_username)
                
                # Clean username (remove @ if present)
                if channel_username.startswith('@'):
                    channel_username = channel_username[1:]
                
                print(f"{idx}. Checking: {channel_name}")
                print(f"   Username: @{channel_username}")
                
                # Get entity
                entity = await self.client.get_entity(channel_username)
                channel_id = entity.id
                
                # Calculate event ID (with -100 prefix)
                event_id = -1000000000000 - channel_id
                
                print(f"   ✅ Channel found - ID: {channel_id}")
                print(f"   📡 Event ID: {event_id}")
                
                # Verify membership
                is_member = await self._verify_membership(entity)
                
                if is_member:
                    # Store entity and add to map with BOTH ID formats
                    self.channel_entities.append(entity)
                    self.channels_map[channel_id] = config
                    self.channels_map[event_id] = config
                    
                    # Show filter info
                    self._print_filter_info(config)
                    print(f"   ✅ WILL LISTEN to this channel")
                else:
                    print(f"   ❌ SKIPPING - Not subscribed/no access")
                
                print()
                
            except Exception as e:
                print(f"{idx}. ❌ Error loading {config.get('username')}: {e}")
                print()
        
        if not self.channel_entities:
            print("="*60)
            print("❌ No valid channels loaded!")
            print("="*60)
            print()
            print("💡 Troubleshooting tips:")
            print("   1. Make sure you're subscribed to all channels")
            print("   2. Check that channel usernames are correct")
            print("   3. Try accessing the channels manually in Telegram first")
            print()
            return False
        
        print("="*60)
        print(f"✅ Setup complete - {len(self.channel_entities)} channels ready")
        print("="*60)
        return True
    
    async def _verify_membership(self, entity):
        """Verify if user is member of channel"""
        try:
            if isinstance(entity, Channel):
                try:
                    await self.client.get_permissions(entity)
                    print(f"   ✅ Membership: Member/Subscriber")
                    return True
                except:
                    # Try to get messages to verify access
                    try:
                        messages = await self.client.get_messages(entity, limit=1)
                        if messages:
                            print(f"   ✅ Access verified: Can read messages")
                            return True
                    except Exception as msg_error:
                        print(f"   ❌ Cannot access messages: {str(msg_error)[:50]}")
                        print(f"   ⚠️  You may NOT be subscribed to this channel!")
                        return False
            else:
                print(f"   ✅ Access: Chat/Group")
                return True
        except Exception as e:
            print(f"   ⚠️  Could not verify membership: {str(e)[:50]}")
            return True  # Try anyway
    
    def _print_filter_info(self, config):
        """Print filter configuration info"""
        filter_config = config.get('filter', {})
        filter_type = filter_config.get('type', 'none')
        filter_value = filter_config.get('value', [])
        
        print(f"   📊 Filter Type: {filter_type}")
        
        if filter_type in ['contains', 'contains_all']:
            keywords = filter_value if isinstance(filter_value, list) else [filter_value]
            print(f"   🔑 Keywords: {', '.join(keywords)}")
        elif filter_type == 'regex':
            print(f"   🔍 Pattern: {filter_value}")
    
    def _get_message_attachments(self, message):
        """
        Extract attachment information from message
        
        Returns:
            List of dicts with attachment info: [{'type': 'Photo', 'name': 'image.jpg', 'size': '1.2 MB'}, ...]
        """
        attachments = []
        
        try:
            # Check for photo
            if message.photo:
                size = self._format_size(message.photo.sizes[-1].size) if hasattr(message.photo.sizes[-1], 'size') else 'Unknown'
                attachments.append({
                    'type': 'Photo',
                    'name': f'photo_{message.id}.jpg',
                    'size': size
                })
            
            # Check for document (files)
            if message.document:
                doc = message.document
                filename = 'unknown_file'
                
                # Try to get filename from attributes
                for attr in doc.attributes:
                    if hasattr(attr, 'file_name'):
                        filename = attr.file_name
                        break
                
                size = self._format_size(doc.size)
                mime_type = doc.mime_type if hasattr(doc, 'mime_type') else 'unknown'
                
                attachments.append({
                    'type': 'Document',
                    'name': filename,
                    'size': size,
                    'mime_type': mime_type
                })
            
            # Check for video
            if message.video:
                video = message.video
                filename = f'video_{message.id}.mp4'
                
                for attr in video.attributes:
                    if hasattr(attr, 'file_name'):
                        filename = attr.file_name
                        break
                
                size = self._format_size(video.size)
                duration = f"{video.duration}s" if hasattr(video, 'duration') else 'Unknown'
                
                attachments.append({
                    'type': 'Video',
                    'name': filename,
                    'size': size,
                    'duration': duration
                })
            
            # Check for audio
            if message.audio:
                audio = message.audio
                filename = f'audio_{message.id}.mp3'
                
                for attr in audio.attributes:
                    if hasattr(attr, 'file_name'):
                        filename = attr.file_name
                        break
                
                size = self._format_size(audio.size)
                duration = f"{audio.duration}s" if hasattr(audio, 'duration') else 'Unknown'
                
                attachments.append({
                    'type': 'Audio',
                    'name': filename,
                    'size': size,
                    'duration': duration
                })
            
            # Check for voice message
            if message.voice:
                voice = message.voice
                size = self._format_size(voice.size)
                duration = f"{voice.duration}s" if hasattr(voice, 'duration') else 'Unknown'
                
                attachments.append({
                    'type': 'Voice',
                    'name': f'voice_{message.id}.ogg',
                    'size': size,
                    'duration': duration
                })
            
            # Check for sticker
            if message.sticker:
                attachments.append({
                    'type': 'Sticker',
                    'name': 'sticker',
                    'size': 'N/A'
                })
            
            # Check for poll
            if message.poll:
                attachments.append({
                    'type': 'Poll',
                    'name': message.poll.question,
                    'size': 'N/A'
                })
            
            # Check for contact
            if message.contact:
                contact_name = f"{message.contact.first_name} {message.contact.last_name or ''}".strip()
                attachments.append({
                    'type': 'Contact',
                    'name': contact_name,
                    'size': 'N/A'
                })
            
            # Check for location
            if message.geo:
                attachments.append({
                    'type': 'Location',
                    'name': f'lat:{message.geo.lat}, lon:{message.geo.long}',
                    'size': 'N/A'
                })
        
        except Exception as e:
            print(f"   ⚠️  Error parsing attachments: {e}")
        
        return attachments
    
    def _format_size(self, size_bytes):
        """Format file size to human readable format"""
        try:
            size_bytes = int(size_bytes)
            
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size_bytes < 1024.0:
                    return f"{size_bytes:.1f} {unit}"
                size_bytes /= 1024.0
            
            return f"{size_bytes:.1f} TB"
        except:
            return "Unknown"
    
    async def start_listening(self, save_state_callback=None):
        """
        Start listening for new messages
        
        Args:
            save_state_callback: Optional function to save state after processing messages
        """
        print("\n" + "="*60)
        print("👂 LISTENING FOR NEW MESSAGES")
        print("="*60)
        print(f"Monitoring {len(self.channel_entities)} channels in real-time...")
        print("Press Ctrl+C to stop")
        print("="*60)
        print()
        
        # Register event handler using entities
        @self.client.on(events.NewMessage(chats=self.channel_entities))
        async def message_handler(event):
            await self.handle_new_message(event, save_state_callback)
        
        # Debug handler to detect other messages
        @self.client.on(events.NewMessage())
        async def debug_handler(event):
            if event.chat_id not in self.channels_map:
                try:
                    chat = await event.get_chat()
                    chat_name = getattr(chat, 'title', getattr(chat, 'first_name', 'Unknown'))
                    print(f"🔔 Debug: Message from other chat: {chat_name} (ID: {event.chat_id})")
                except:
                    pass
        
        # Keep running
        await self.client.run_until_disconnected()
    
    async def handle_new_message(self, event, save_state_callback=None):
        """
        Handle incoming new message
        
        Args:
            event: Telegram message event
            save_state_callback: Optional function to save state
        """
        try:
            channel_id = event.chat_id
            message = event.message
            
            # Check if from monitored channel
            if channel_id not in self.channels_map:
                print(f"⚠️  Message from unmonitored channel ID: {channel_id}")
                return
            
            config = self.channels_map[channel_id]
            channel_name = config.get('name', 'Unknown')
            filter_config = config.get('filter')
            
            # Check if already processed
            if channel_id in self.state['last_message_ids']:
                if message.id <= self.state['last_message_ids'][channel_id]:
                    return
            
            # Update state
            self.state['last_message_ids'][channel_id] = message.id
            if save_state_callback:
                save_state_callback()
            
            # Detect attachments
            attachments = self._get_message_attachments(message)
            
            # Check if message has text
            if not message.text:
                if attachments:
                    print(f"   ℹ️  {channel_name}: Message has only attachments (ID: {message.id})")
                    for att in attachments:
                        print(f"      📎 {att['type']}: {att['name']}")
                else:
                    print(f"   ⚠️  {channel_name}: Message has no text (ID: {message.id})")
                return
            
            # Apply filter
            if not BotFilter.apply_filter(message.text, filter_config):
                print(f"   ⚠️  {channel_name}: Message filtered out (ID: {message.id})")
                return
            
            # Message passed filter - process it
            is_own_message = message.sender_id == self.me.id
            
            msg_data = {
                'date': message.date.strftime('%Y-%m-%d %H:%M:%S'),
                'text': message.text,
                'id': message.id,
                'attachments': attachments
            }
            
            print(f"\n{'='*60}")
            print(f"🔔 NEW MESSAGE: {channel_name}")
            print(f"{'='*60}")
            print(f"   ID: {message.id}")
            print(f"   Date: {msg_data['date']}")
            if is_own_message:
                print(f"   ⚠️  This is YOUR message")
            if attachments:
                print(f"   📎 Attachments: {len(attachments)}")
                for att in attachments:
                    print(f"      • {att['type']}: {att['name']} ({att['size']})")
            print(f"   Preview: {message.text[:100]}...")
            print(f"{'='*60}")
            
            # Send email notification
            email_subject = f"[New] {config.get('email_subject', channel_name)}"
            template = config.get('template', 'breach')
            
            html_content = EmailTemplate.create_email(channel_name, msg_data, template)
            EmailService.send_email(email_subject, html_content)
                
        except Exception as e:
            print(f"❌ Error handling message: {e}")
            import traceback
            traceback.print_exc()