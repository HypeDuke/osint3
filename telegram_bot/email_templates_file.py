import re
import json
from datetime import datetime


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
            return any(keyword.lower() in message_text.lower() for keyword in keywords)
        elif filter_type == 'contains_all':
            return all(keyword.lower() in message_text.lower() for keyword in keywords)
        elif filter_type == 'starts_with':
            return any(message_text.lower().startswith(keyword.lower()) for keyword in keywords)
        elif filter_type == 'ends_with':
            return any(message_text.lower().endswith(keyword.lower()) for keyword in keywords)
        elif filter_type == 'regex':
            return bool(re.search(filter_value, message_text, re.IGNORECASE))
        elif filter_type == 'not_contains':
            return not any(keyword.lower() in message_text.lower() for keyword in keywords)
        
        return True


class EmailTemplate:
    """Email templates"""
    
    @staticmethod
    def parse_message_data(text):
        """Parse structured data from message text"""
        source = content = detection_date = title = None
        parse_success = False
        
        if '"Source":' in text or '"source":' in text.lower():
            try:
                # Method 1: Direct JSON parse
                try:
                    data = json.loads(text)
                    source = data.get('Source', data.get('source', ''))
                    content = data.get('Content', data.get('content', ''))
                    detection_date = data.get('Detection Date', data.get('detection_date', ''))
                    title = data.get('Title', data.get('title', ''))
                    if source or content or detection_date or title:
                        parse_success = True
                except:
                    # Method 2: Extract JSON part before ** markers
                    json_part = text
                    if '**' in text:
                        json_part = text.split('**')[0].strip()
                    elif '🔹' in text:
                        json_part = text.split('🔹')[0].strip()
                    elif '\n\n' in text:
                        json_part = text.split('\n\n')[0].strip()
                    
                    # Method 3: Use regex to extract field by field
                    source_match = re.search(r'"Source"\s*:\s*"([^"]+)"', json_part, re.IGNORECASE)
                    if source_match:
                        source = source_match.group(1)
                    
                    title_match = re.search(r'"Title"\s*:\s*"([^"]+)"', json_part, re.IGNORECASE)
                    if title_match:
                        title = title_match.group(1)
                    
                    content_match = re.search(r'"Content"\s*:\s*"([^"]+?)"\s*,\s*"', json_part, re.IGNORECASE | re.DOTALL)
                    if content_match:
                        content = content_match.group(1)
                    
                    date_match = re.search(r'"Detection Date"\s*:\s*"([^"]+)"', json_part, re.IGNORECASE)
                    if date_match:
                        detection_date = date_match.group(1)
                    
                    if source or content or detection_date or title:
                        parse_success = True
            except Exception:
                pass
        
        # Clean content: remove "Visit the link..." sentence
        if content:
            content = re.sub(r'Visit the link.*?\.\.\.', '', content, flags=re.IGNORECASE | re.DOTALL).strip()
        
        return parse_success, source, content, detection_date, title
    
    @staticmethod
    def create_email(channel_name, message, template='breach'):
        """Create email for a message"""
        if template == 'breach':
            return EmailTemplate.breach_template(channel_name, message)
        elif template == 'cve':
            return EmailTemplate.cve_template(channel_name, message)
        else:
            return EmailTemplate.minimal_template(channel_name, message)
    
    @staticmethod
    def create_batch_email(channel_name, messages, template='breach'):
        """Create email for multiple messages (initial search)"""
        if template == 'breach':
            return EmailTemplate.breach_batch_template(channel_name, messages)
        elif template == 'cve':
            return EmailTemplate.cve_batch_template(channel_name, messages)
        else:
            return EmailTemplate.minimal_batch_template(channel_name, messages)
    
    @staticmethod
    def minimal_template(channel_name, message):
        """Minimal template for single message"""
        formatted_text = message['text'].replace('\n', '<br>')
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h3>🔔 New Message: {channel_name}</h3>
            <p><small>{message['date']}</small></p>
            <div style="background: #f5f5f5; padding: 15px; border-left: 3px solid #333;">
                {formatted_text}
            </div>
        </body>
        </html>
        """
        return html
       
    @staticmethod
    def breach_template(channel_name, message):
        """Breach detector template for single message"""
        parse_success, source, content, detection_date, title = EmailTemplate.parse_message_data(message['text'])
        
        if parse_success and (source or content or detection_date):
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
                        <h1>🔒 Data Breach Alert</h1>
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
            formatted_text = message['text'].replace('\n', '<br>')
            html = f"""
            <html>
            <body style="font-family: 'Courier New', monospace; margin: 0; padding: 40px; background: white; color: #000;">
                <div style="border-bottom: 1px solid #000; padding-bottom: 10px; margin-bottom: 20px;">
                    <strong>🔔 NEW: {channel_name}</strong><br>
                    <small>{message['date']}</small>
                </div>
                <div style="line-height: 1.6;">
                    {formatted_text}
                </div>
            </body>
            </html>
            """
        return html
    
    @staticmethod
    def cve_template(channel_name, message):
        """CVE detector template for single message"""
        parse_success, source, content, detection_date, title = EmailTemplate.parse_message_data(message['text'])
        
        if parse_success and (title or content):
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
                            <div class="field-value">{formatted_content}</div>
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
            formatted_text = message['text'].replace('\n', '<br>')
            html = f"""
            <html>
            <body style="font-family: 'Courier New', monospace; margin: 0; padding: 40px; background: white; color: #000;">
                <div style="border-bottom: 1px solid #000; padding-bottom: 10px; margin-bottom: 20px;">
                    <strong>🔔 NEW: {channel_name}</strong><br>
                    <small>{message['date']}</small>
                </div>
                <div style="line-height: 1.6;">
                    {formatted_text}
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
            formatted_text = msg['text'].replace('\n', '<br>')
            html += f"""
            <div style="background: #f9f9f9; padding: 15px; margin: 15px 0; border-left: 3px solid #333;">
                <strong>#{idx}</strong> - <small>{msg['date']}</small><br><br>
                {formatted_text}
            </div>
            """
        
        html += """
        </body>
        </html>
        """
        return html  

    @staticmethod
    def breach_batch_template(channel_name, messages):
        """Breach detector batch template"""
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 40px auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: white; padding: 35px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 28px; font-weight: 600; color: blue; }}
                .header p {{ margin: 8px 0 0 0; opacity: 0.9; font-size: 15px; }}
                .summary {{ padding: 25px 35px; background: #e3f2fd; border-bottom: 1px solid #e0e0e0; }}
                .summary-item {{ display: inline-block; margin-right: 30px; }}
                .summary-label {{ font-size: 11px; text-transform: uppercase; color: #1e3c72; font-weight: 600; }}
                .summary-value {{ font-size: 24px; color: #1e3c72; font-weight: 600; }}
                .content {{ padding: 35px; }}
                .alert-item {{ background: white; border: 1px solid #e0e0e0; border-radius: 6px; margin-bottom: 20px; overflow: hidden; }}
                .alert-header {{ background: #f8f9fa; padding: 15px 20px; border-bottom: 1px solid #e0e0e0; }}
                .alert-number {{ font-weight: 600; color: #1e3c72; }}
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
                    <h1>🔒 Data Breach Report</h1>
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
            parse_success, source, content, detection_date, title = EmailTemplate.parse_message_data(msg['text'])
            
            if not parse_success or not (source or content or detection_date):
                formatted_text = msg['text'].replace('\n', '<br>')
                html += f"""
                    <div class="alert-item">
                        <div class="alert-header">
                            <span class="alert-number">Alert #{idx}</span>
                            <span style="float: right; color: #999; font-size: 12px;">ID: {msg['id']}</span>
                        </div>
                        <div class="alert-body">
                            <div class="field">
                                <div class="field-label">Raw Message Content</div>
                                <div class="field-value">{formatted_text}</div>
                            </div>
                        </div>
                    </div>
                """
            else:
                html += f"""
                    <div class="alert-item">
                        <div class="alert-header">
                            <span class="alert-number">Alert #{idx}</span>
                            <span style="float: right; color: #999; font-size: 12px;">ID: {msg['id']}</span>
                        </div>
                        <div class="alert-body">
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
                    </div>
                """
        
        html += f"""
                </div>
                <div class="footer">
                    <div>Initial search completed on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
                    <div style="margin-top: 5px; color: #999;">This is an automated data breach report</div>
                </div>
            </div>
        </body>
        </html>
        """
        return html

    @staticmethod
    def cve_batch_template(channel_name, messages):
        """CVE detector batch template"""
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5; }}
                .container {{ max-width: 850px; margin: 40px auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #c62828 0%, #e53935 100%); color: white; padding: 35px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 28px; font-weight: 600; color: red; }}
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
            parse_success, source, content, detection_date, title = EmailTemplate.parse_message_data(msg['text'])
            
            if not parse_success or not (title or content):
                formatted_text = msg['text'].replace('\n', '<br>')
                html += f"""
                    <div class="cve-item">
                        <div class="cve-header">
                            <span class="cve-number">CVE #{idx}</span>
                            <span style="float: right; color: #999; font-size: 12px;">ID: {msg['id']}</span>
                        </div>
                        <div class="cve-body">
                            <div class="field">
                                <div class="field-label">Raw Message Content</div>
                                <div class="field-value">{formatted_text}</div>
                            </div>
                        </div>
                    </div>
                """
            else:
                formatted_content = content.replace('\n', '<br>') if content else 'N/A'
                html += f"""
                    <div class="cve-item">
                        <div class="cve-header">
                            <span class="cve-number">CVE #{idx}</span>
                            <span class="cve-badge">VULNERABILITY</span>
                            <span style="float: right; color: #999; font-size: 12px;">ID: {msg['id']}</span>
                        </div>
                        <div class="cve-body">
                            <div class="title-section">
                                <div class="title-value">{title if title else 'N/A'}</div>
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
        return html