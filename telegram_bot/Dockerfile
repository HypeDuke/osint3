FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all module files
COPY email_service.py .
COPY channel_search.py .
COPY realtime_listener.py .
COPY email_templates_file.py .
COPY monitor.py .
COPY channels.json .

# Create directories for session files and logs
RUN mkdir -p /app/sessions /app/logs

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the main monitor
CMD ["python", "monitor.py"]