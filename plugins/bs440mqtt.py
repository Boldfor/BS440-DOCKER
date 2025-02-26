import paho.mqtt.client as mqtt
import json
from datetime import datetime
from .plugin_base import PluginBase

class BS440mqtt(PluginBase):
    """Plugin to publish data to an MQTT broker."""
    
    def __init__(self, config, logger):
        super().__init__(config, logger)
        
        # Read MQTT configuration
        self.mqtt_host = config.get('MQTT', 'host', fallback='localhost')
        self.mqtt_port = config.getint('MQTT', 'port', fallback=1883)
        self.mqtt_username = config.get('MQTT', 'username', fallback=None)
        self.mqtt_password = config.get('MQTT', 'password', fallback=None)
        self.mqtt_prefix = config.get('MQTT', 'prefix', fallback='medisana/bs440')
        self.mqtt_retain = config.getboolean('MQTT', 'retain', fallback=True)
        self.mqtt_qos = config.getint('MQTT', 'qos', fallback=0)
        
        # Initialize MQTT client
        self.client = mqtt.Client()
        if self.mqtt_username and self.mqtt_password:
            self.client.username_pw_set(self.mqtt_username, self.mqtt_password)
        
        try:
            self.client.connect(self.mqtt_host, self.mqtt_port, 60)
            self.client.loop_start()
            self.logger.info(f"Connected to MQTT broker at {self.mqtt_host}:{self.mqtt_port}")
        except Exception as e:
            self.logger.error(f"Failed to connect to MQTT broker: {str(e)}")
    
    def __del__(self):
        """Clean up MQTT connection on object destruction."""
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except:
            pass
    
    def process_measurement(self, measurement):
        """Process a single measurement and publish to MQTT."""
        if not measurement:
            return
        
        # Skip person data
        if measurement.get('type') == 'person':
            return
        
        person_id = measurement.get('person', 0)
        measurement_type = measurement.get('type', 'unknown')
        
        # Create topic based on measurement type and person
        topic = f"{self.mqtt_prefix}/person{person_id}/{measurement_type}"
        
        # Convert timestamp to ISO format if present
        if 'timestamp' in measurement and isinstance(measurement['timestamp'], datetime):
            measurement = measurement.copy()  # Create a copy to avoid modifying the original
            measurement['timestamp'] = measurement['timestamp'].isoformat()
        
        # Convert to JSON and publish
        payload = json.dumps(measurement)
        
        try:
            self.client.publish(topic, payload, qos=self.mqtt_qos, retain=self.mqtt_retain)
            self.logger.debug(f"Published to {topic}: {payload}")
        except Exception as e:
            self.logger.error(f"Failed to publish to MQTT: {str(e)}") 
