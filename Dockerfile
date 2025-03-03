FROM python:3.9-slim

# Install required system packages including build dependencies
RUN apt-get update && apt-get install -y \
    bluetooth \
    bluez \
    python3-bluez \
    build-essential \
    gcc \
    make \
    libbluetooth-dev \
    pkg-config \
    libglib2.0-dev \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip3 install paho-mqtt

# Copy the rest of the application
COPY . .

# Run the scanner script
CMD ["python", "ble_scanner.py"]
