FROM debian:trixie-slim

LABEL maintainer="@jay_townsend1 & @NotoriousRebel1"

# Install dependencies for building Python from source
RUN apt update && apt install -y \
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

# Install Python 3.13.6 from source
RUN curl -fsSL https://www.python.org/ftp/python/3.13.6/Python-3.13.6.tgz -o Python-3.13.6.tgz \
    && tar -xvf Python-3.13.6.tgz \
    && cd Python-3.13.6 \
    && ./configure --enable-optimizations \
    && make -j 4 \
    && make altinstall \
    && rm -rf /Python-3.13.6 /Python-3.13.6.tgz

# Install pip for Python 3.13
RUN curl https://bootstrap.pypa.io/get-pip.py | python3.13

# Clone theHarvester repository
WORKDIR /app
RUN git clone https://github.com/laramies/theHarvester.git

# Install theHarvester dependencies
WORKDIR /app/theHarvester
RUN python3.13 -m pip install --upgrade pip setuptools wheel \
    && python3.13 -m pip install --no-cache-dir .

# Expose API port
EXPOSE 5100

# Run restfulHarvest on port 5100
ENTRYPOINT ["python3.13", "restfulHarvest.py", "-b", "0.0.0.0", "-p", "5100"]
