"""
Channel Search Module
Handles initial historical search of channels
"""
import asyncio
from telethon.errors import FloodWaitError
from email_templates_file import EmailTemplate, BotFilter
from email_service import EmailService


class ChannelSearcher:
    """Handles initial search through channel history"""
    
    def __init__(self, client, state):
        """
        Initialize searcher
        
        Args:
            client: Telethon client instance
            state: State dictionary with initialized_channels and last_message_ids
        """
        self.client = client
        self.state = state
    
    async def initial_search(self, config, ensure_connected_callback=None):
        """
        Search channel history for keyword on first run
        
        Args:
            config: Channel configuration dict
            ensure_connected_callback: Optional async function to ensure connection
        
        Returns:
            channel_id if successful, None otherwise
        """
        channel_username = config.get('username')
        channel_name = config.get('name', channel_username)
        filter_config = config.get('filter')
        search_limit = config.get('search_limit', 1000)
        
        print(f"\n{'='*60}")
        print(f"🔍 INITIAL SEARCH: {channel_name}")
        print(f"{'='*60}")
        
        try:
            # Ensure connected before operation
            if ensure_connected_callback:
                if not await ensure_connected_callback():
                    print(f"   ❌ Cannot connect, skipping {channel_name}")
                    return None
            
            # Clean username
            if channel_username.startswith('@'):
                channel_username = channel_username[1:]
            
            entity = await self.client.get_entity(channel_username)
            channel_id = entity.id
            
            # Store with both ID formats (positive and -100 prefix)
            event_id = -1000000000000 - channel_id
            
            # Check if already initialized
            if channel_id in self.state['initialized_channels']:
                print(f"   ⏭️  Already searched, skipping initial search")
                return channel_id
            
            # Extract search keywords from filter
            search_keywords = []
            if filter_config and filter_config.get('type') in ['contains', 'contains_all']:
                filter_value = filter_config.get('value')
                if isinstance(filter_value, list):
                    search_keywords = filter_value
                elif isinstance(filter_value, str):
                    search_keywords = [k.strip() for k in filter_value.split(',')]
            
            matched_messages = []
            seen_message_ids = set()
            
            # Search for keywords
            if search_keywords:
                print(f"   🔎 Searching for {len(search_keywords)} keywords")
                print(f"   ⏳ This may take a while...")
                
                for idx, keyword in enumerate(search_keywords, 1):
                    print(f"      [{idx}/{len(search_keywords)}] Searching: '{keyword}'...")
                    
                    try:
                        # Ensure connected before each search
                        if ensure_connected_callback:
                            if not await ensure_connected_callback():
                                print(f"      ⚠️  Connection lost, skipping keyword '{keyword}'")
                                continue
                        
                        async for message in self.client.iter_messages(
                            entity, 
                            limit=search_limit,
                            search=keyword
                        ):
                            if message.text and message.id not in seen_message_ids:
                                if BotFilter.apply_filter(message.text, filter_config):
                                    matched_messages.append({
                                        'date': message.date.strftime('%Y-%m-%d %H:%M:%S'),
                                        'text': message.text,
                                        'id': message.id
                                    })
                                    seen_message_ids.add(message.id)
                    
                    except FloodWaitError as e:
                        print(f"      ⏸️  Flood wait: {e.seconds}s, waiting...")
                        await asyncio.sleep(e.seconds)
                    except Exception as e:
                        print(f"      ⚠️  Error searching '{keyword}': {e}")
                        continue
                
                matched_messages.sort(key=lambda x: x['date'], reverse=True)
                print(f"   ✅ Found {len(matched_messages)} unique messages")
            
            else:
                # No keywords - get recent messages
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
            
            # Send email if messages found
            if matched_messages:
                self._print_search_summary(matched_messages)
                
                template = config.get('template', 'breach')
                email_subject = f"[Napas Osint] {config.get('email_subject', channel_name)}"
                
                html_content = EmailTemplate.create_batch_email(
                    channel_name, 
                    matched_messages,
                    template
                )
                
                print(f"   📧 Sending batch email with {len(matched_messages)} messages...")
                EmailService.send_email(email_subject, html_content)
            
            # Update state with latest message ID
            latest_messages = await self.client.get_messages(entity, limit=1)
            if latest_messages:
                # Store with both ID formats
                self.state['last_message_ids'][channel_id] = latest_messages[0].id
                self.state['last_message_ids'][event_id] = latest_messages[0].id
                print(f"   📍 Latest message ID: {latest_messages[0].id}")
            
            # Mark as initialized
            self.state['initialized_channels'].append(channel_id)
            
            print(f"   ✅ Initial search completed")
            return channel_id
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _print_search_summary(self, matched_messages):
        """Print summary of search results"""
        print(f"\n   📊 SEARCH RESULTS SUMMARY:")
        print(f"   {'='*50}")
        print(f"   Total messages found: {len(matched_messages)}")
        print(f"   {'='*50}")
        
        preview_count = min(3, len(matched_messages))
        for idx, msg in enumerate(matched_messages[:preview_count], 1):
            print(f"\n   Message #{idx}:")
            print(f"   Date: {msg['date']}")
            print(f"   ID: {msg['id']}")
            preview_text = msg['text'][:200].replace('\n', ' ')
            print(f"   Preview: {preview_text}...")
            print(f"   {'-'*50}")
        
        if len(matched_messages) > preview_count:
            print(f"\n   ... and {len(matched_messages) - preview_count} more messages")
        
        print(f"\n   {'='*50}")