FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy simple test script
COPY simple_test.py .

# Create directory for session files
RUN mkdir -p /app/sessions /app/logs

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the simple test
CMD ["python", "multi_bot_telegram.py"]