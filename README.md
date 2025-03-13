# BS440-Docker

A Docker-based implementation of the [BS440 project](https://github.com/keptenkurk/BS440/) for Medisana scales.

## Overview

This project provides a containerized solution for connecting to Medisana scales via Bluetooth Low Energy (BLE) and processing the measurement data. It includes:

- BLE connection and data retrieval
- Time synchronization with the scale
- Plugin system for data processing (MQTT, CSV, etc.)
- Docker deployment for easy setup

## Features

- **Docker Integration**: Run in a containerized environment
- **Plugin Architecture**: Extensible design for various data outputs
- **MQTT Support**: Publish measurements to MQTT brokers
- **Time Synchronization**: Ensures accurate timestamps on measurements
- **Historical Data Handling**: Processes both new and stored measurements

## Getting Started

### Prerequisites

- Docker and Docker Compose
- A Medisana scale (BS440, BS444, etc.)
- Bluetooth capability on the host machine

### Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/BS440-Docker.git
   cd BS440-Docker
   ```

2. Configure your scale's MAC address in `BS440.ini`:
   ```
   [BLE_Settings]
   mac_address = XX:XX:XX:XX:XX:XX
   ```

3. Start the container:
   ```
   docker-compose up -d
   ```

## Configuration

After deploying the container, edit the `BS440.ini` file under /app/config/ to configure:

```ini
[BLE_Settings]
# MAC address of the device to monitor (comma-separated if multiple)
mac_address = XX:XX:XX:XX:XX:XX

[Logging]
# Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
level = INFO

[Plugins]
plugins = BS440mqtt

[MQTT]
host = localhost
port = 1883
username = your_mqtt_username
password = your_mqtt_password
prefix = medisana/bs440
retain = True
qos = 0
```

## Plugin System

The project uses a plugin architecture to process and store measurement data:

- **BS440mqtt**: Publishes data to MQTT brokers for integration with home automation systems
- More plugins coming soon (CSV, InfluxDB, Google Fit, etc.)

### MQTT Topics

Data is published to the following MQTT topics:

- `medisana/bs440/person{id}/weight` - Weight measurements
- `medisana/bs440/person{id}/body` - Body composition measurements (fat, muscle, etc.)

## Troubleshooting

### Bluetooth Connectivity

If you're having trouble connecting to your scale:

1. Ensure Bluetooth is enabled on your host machine
2. Verify the scale's MAC address is correct in the configuration
3. Check that the scale is in pairing mode (usually by stepping on and off)
4. Run with `level = DEBUG` for more detailed logs

### Docker Issues

The container requires privileged access for Bluetooth functionality. If you're experiencing issues:

1. Ensure the container has access to `/var/run/dbus` and `/var/run/bluetooth`
2. Verify that `network_mode: host` is set in your docker-compose.yml
3. Check that the Bluetooth service is running on the host

## Contributing

Contributions are welcome! Feel free to submit pull requests or open issues for:

- Additional plugins
- Bug fixes
- Documentation improvements
- Feature requests

## Acknowledgments

This project is based on the original [BS440 project](https://github.com/keptenkurk/BS440/) by keptenkurk. It extends the functionality with Docker support and an improved plugin architecture.
