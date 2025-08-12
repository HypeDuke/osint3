FROM python:3.11-slim

# Cài đặt các thư viện cần thiết
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libssl-dev \
    zlib1g-dev \
    libbz2-dev \
    libreadline-dev \
    libsqlite3-dev \
    wget \
    llvm \
    libncurses5-dev \
    libncursesw5-dev \
    xz-utils \
    tk-dev \
    libffi-dev \
    liblzma-dev \
    python3-dev \
    git \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Clone repo theHarvester trực tiếp từ GitHub
WORKDIR /app
RUN git clone https://github.com/laramies/theHarvester.git

# Cài đặt dependencies từ pyproject.toml (nếu có)
WORKDIR /app/theHarvester
RUN pip install --no-cache-dir .

# Chạy API của theHarvester tại port 5100
EXPOSE 5100
CMD ["python", "restfulHarvest.py", "-b", "0.0.0.0", "-p", "5100"]
