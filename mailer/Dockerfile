FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy mailer code
COPY mailer.py .

# Expose nothing (this is background worker)
# EXPOSE not needed

# Run mailer
CMD ["python", "mailer.py"]
