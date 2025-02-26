import logging
import configparser
from bluepy import btle
import time
from datetime import datetime
from medisana import MedisanaBS440
import struct
import importlib
import os
import sys

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)

def read_config():
    config = configparser.ConfigParser()
    config.read('BS440.ini')
    
    mac_addresses = [
        addr.strip() 
        for addr in config['BLE_Settings']['mac_address'].split(',')
    ]
    
    log_level = getattr(logging, config['Logging']['level'].upper())
    return config, mac_addresses, log_level

def load_plugins(config, logger):
    """Load all enabled plugins."""
    plugins = []
    
    # Ensure plugins directory is in the Python path
    plugins_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plugins')
    if plugins_dir not in sys.path:
        sys.path.insert(0, plugins_dir)
    
    # Get enabled plugins from config
    plugin_names = config.get('Plugins', 'plugins', fallback='').split(',')
    plugin_names = [name.strip() for name in plugin_names if name.strip()]
    
    for plugin_name in plugin_names:
        try:
            module_name = f"plugins.{plugin_name.lower()}"
            module = importlib.import_module(module_name)
            plugin_class = getattr(module, plugin_name)
            plugin = plugin_class(config, logger)
            plugins.append(plugin)
            logger.info(f"Loaded plugin: {plugin_name}")
        except Exception as e:
            logger.error(f"Failed to load plugin {plugin_name}: {str(e)}")
    
    return plugins

class BLEScanner(btle.DefaultDelegate):
    def __init__(self, target_macs, logger):
        btle.DefaultDelegate.__init__(self)
        self.target_macs = [mac.lower() for mac in target_macs]
        self.logger = logger
        self.scanner = btle.Scanner()
        self.medisana = MedisanaBS440(logger)
        self.plugins = []
    
    def handleNotification(self, handle, data):
        """Handle incoming notifications from the scale"""
        self.logger.debug(f"Received notification on handle {handle}: {data.hex()}")
        measurement = self.medisana.parse_measurement(data)
        if measurement:
            self.logger.info(f"Processed measurement: {measurement}")

    def connect_to_device(self, device_addr):
        """Returns True if connection and data exchange was successful"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self.logger.info(f"Connection attempt {attempt + 1}/{max_retries}")
                self.logger.debug("Creating Peripheral object...")
                peripheral = btle.Peripheral(device_addr)
                peripheral.withDelegate(self)
                self.logger.info("Successfully connected!")
                
                try:
                    self.logger.debug("Discovering services...")
                    services = peripheral.services
                    if not services:
                        self.logger.debug("No services found, attempting discovery...")
                        services = peripheral.discoverServices()
                    
                    weight_service_uuid = "000078b2-0000-1000-8000-00805f9b34fb"
                    write_char_uuid = "00008a81-0000-1000-8000-00805f9b34fb"
                    
                    for service in services:
                        if str(service.uuid).lower() == weight_service_uuid:
                            self.logger.info("Found weight measurement service!")
                            write_char = None
                            
                            # Enable notifications for all INDICATE characteristics
                            for char in service.getCharacteristics():
                                if char.propertiesToString().find('INDICATE') >= 0:
                                    self.logger.debug(f"Enabling notifications for {char.uuid}")
                                    peripheral.writeCharacteristic(char.getHandle() + 1, b"\x02\x00", withResponse=True)
                            
                            # Find the write characteristic for commands
                            for char in service.getCharacteristics():
                                if str(char.uuid).lower() == write_char_uuid:
                                    write_char = char
                                    break
                            
                            if write_char:
                                self.logger.debug("Sending initialization commands...")
                                write_char.write(b"\x01", withResponse=True)  # Start measurement mode
                                
                                # Send time synchronization command
                                # The time_offset should be 1262304000 for BS410/BS444 models (Jan 1, 2010)
                                time_offset = 1262304000
                                if self.send_time_sync_command(peripheral, write_char.getHandle(), time_offset):
                                    self.logger.info("Scale time synchronized")
                                else:
                                    self.logger.warning("Failed to synchronize scale time")
                                
                                # Wait for notifications
                                self.logger.info("Waiting for measurements...")
                                self.logger.info("Please step on the scale now...")
                                
                                timeout = 30  # Seconds
                                self.logger.info(f"Waiting for {timeout} seconds to receive all stored measurements...")
                                start_time = time.time()
                                while time.time() - start_time < timeout:
                                    if peripheral.waitForNotifications(1.0):
                                        # Notifications received, continue waiting
                                        continue
                                    # No notifications received for 1 second, but keep waiting until timeout
                                
                                # After receiving all measurements, process with plugins
                                if hasattr(self, 'plugins') and self.plugins and hasattr(self.medisana, 'measurements'):
                                    sorted_measurements = sorted(
                                        self.medisana.measurements,
                                        key=lambda k: k.get('timestamp', datetime.min),
                                        reverse=True
                                    )
                                    
                                    for plugin in self.plugins:
                                        try:
                                            plugin.process_measurements(sorted_measurements)
                                        except Exception as e:
                                            self.logger.error(f"Error in plugin {plugin.name}: {str(e)}")

                finally:
                    self.logger.debug("Attempting to disconnect...")
                    peripheral.disconnect()
                    self.logger.info("Disconnected from device")
                
                return True  # Successfully completed
                
            except btle.BTLEDisconnectError as e:
                self.logger.warning(f"Device disconnected during attempt {attempt + 1}: {str(e)}")
                time.sleep(1)  # Wait before retry
            except btle.BTLEException as e:
                self.logger.warning(f"Connection failed on attempt {attempt + 1}: {str(e)}")
                time.sleep(1)  # Wait before retry
            except Exception as e:
                self.logger.error(f"Unexpected error during connection: {str(e)}", exc_info=True)
                break
        
        return False

    def scan_devices(self):
        try:
            while True:  # Keep scanning until we successfully connect
                self.logger.info("Starting BLE scan...")
                devices = self.scanner.scan(timeout=3.0)  # Shorter scan intervals
                
                for dev in devices:
                    device_mac = dev.addr.lower()
                    
                    if device_mac in self.target_macs:
                        self.logger.info(f"Found target device: {dev.addr}")
                        self.logger.info(f"  RSSI: {dev.rssi} dB")
                        self.logger.info(f"  Address type: {dev.addrType}")
                        
                        for (adtype, desc, value) in dev.getScanData():
                            self.logger.info(f"  {desc}: {value}")
                        
                        # Attempt to connect immediately when we find our target device
                        if self.connect_to_device(dev.addr):
                            return True  # Successfully connected and completed
                    else:
                        self.logger.debug(f"Ignored device: {dev.addr}")
                
                # Short sleep before next scan attempt
                time.sleep(1)
                
        except btle.BTLEException as e:
            self.logger.error(f"Bluetooth error: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error: {str(e)}")
        
        return False

    def send_time_sync_command(self, device, command_characteristic, time_offset):
        """
        Sends the current time to the scale to synchronize its internal clock.
        This is critical for getting correct timestamps in measurements.
        
        The scale expects the Unix timestamp in little endian order preceded by 0x02.
        """
        try:
            # Create timestamp bytearray in the format the scale expects
            # Current time minus the offset (to convert to scale's time base)
            timestamp = bytearray(struct.pack('<I', int(time.time() - time_offset)))
            timestamp.insert(0, 2)  # Prepend with 0x02 as required by the protocol
            
            self.logger.debug(f"Sending time sync command: {timestamp.hex()}")
            
            # Write to the command characteristic
            device.writeCharacteristic(command_characteristic, timestamp, withResponse=True)
            self.logger.info("Time synchronization command sent to scale")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send time sync command: {str(e)}")
            return False

def main():
    logger = setup_logging()
    
    try:
        config, target_macs, log_level = read_config()
        logger.setLevel(log_level)
        
        logger.info("BLE Scanner starting up...")
        logger.info(f"Monitoring devices: {', '.join(target_macs)}")
        
        scanner = BLEScanner(target_macs, logger)
        
        # Load plugins
        scanner.plugins = load_plugins(config, logger)
        
        while True:
            if not scanner.scan_devices():
                logger.info("Connection attempt failed, waiting before retry...")
                time.sleep(5)  # Wait between full retry cycles
            
    except KeyboardInterrupt:
        logger.info("Scanner stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        raise

if __name__ == "__main__":
    main() 