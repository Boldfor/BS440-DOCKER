import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime
from plugins.plugin_base import PluginBase

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
        self.connected = False  # Track connection status
        # Track most recent measurement per person per type: {(person_id, type): measurement}
        self.most_recent = {}
        if self.mqtt_username and self.mqtt_password:
            self.client.username_pw_set(self.mqtt_username, self.mqtt_password)
            self.logger.debug("MQTT credentials configured")
        
        # Set up callbacks for connection status
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_publish = self.on_publish
        
        try:
            self.logger.info(f"Connecting to MQTT broker at {self.mqtt_host}:{self.mqtt_port}")
            self.logger.debug(f"MQTT configuration - Username: {'set' if self.mqtt_username else 'not set'}, "
                            f"Prefix: {self.mqtt_prefix}, QoS: {self.mqtt_qos}, Retain: {self.mqtt_retain}")
            self.client.connect(self.mqtt_host, self.mqtt_port, 60)
            self.client.loop_start()
            self.logger.debug("MQTT client loop started, waiting for connection callback...")
            # Give the connection a moment to establish
            time.sleep(0.5)
            if self.connected:
                self.logger.debug("MQTT connection confirmed")
            else:
                self.logger.warning("MQTT connection not yet established, will retry on first publish")
        except Exception as e:
            self.logger.error(f"Failed to connect to MQTT broker: {str(e)}", exc_info=True)
            self.connected = False
    
    def on_connect(self, client, userdata, flags, rc):
        """Callback for when the client connects to the broker."""
        self.connected = (rc == 0)
        if rc == 0:
            self.logger.info(f"Successfully connected to MQTT broker at {self.mqtt_host}:{self.mqtt_port}")
            self.logger.debug(f"Connection flags: {flags}")
        else:
            rc_messages = {
                1: "Connection refused - incorrect protocol version",
                2: "Connection refused - invalid client identifier",
                3: "Connection refused - server unavailable",
                4: "Connection refused - bad username or password",
                5: "Connection refused - not authorised"
            }
            error_msg = rc_messages.get(rc, f"Unknown error code: {rc}")
            self.logger.error(f"Failed to connect to MQTT broker: {error_msg} (result code: {rc})")
    
    def on_disconnect(self, client, userdata, rc):
        """Callback for when the client disconnects from the broker."""
        self.connected = False
        if rc != 0:
            self.logger.warning(f"Unexpected disconnection from MQTT broker (result code: {rc})")
        else:
            self.logger.info("Disconnected from MQTT broker")
    
    def on_publish(self, client, userdata, mid):
        """Callback for when a message is published."""
        self.logger.debug(f"on_publish callback received for message ID {mid}")
    
    def __del__(self):
        """Clean up MQTT connection on object destruction."""
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except:
            pass
    
    def process_measurement(self, measurement):
        """Track a measurement to find the most recent per person per type.
        
        Since timestamps from the scale can be corrupted, we use the order of
        measurements instead - the last measurement received is the most recent.
        """
        self.logger.debug(f"process_measurement called with: {measurement}")
        
        if not measurement:
            self.logger.debug("Measurement is None or empty, skipping")
            return
        
        # Skip person data
        if measurement.get('type') == 'person':
            self.logger.debug(f"Skipping person data measurement: {measurement}")
            return
        
        person_id = measurement.get('person', 0)
        measurement_type = measurement.get('type', 'unknown')
        key = (person_id, measurement_type)
        
        # Simply keep the last measurement we see for each person/type combination
        # Since measurements come in chronological order, the last one is the most recent
        self.most_recent[key] = measurement
        self.logger.debug(f"Tracking measurement for person {person_id}, type {measurement_type} (will be overwritten if newer measurement arrives)")
    
    def _publish_measurement(self, measurement):
        """Internal method to publish a single measurement to MQTT."""
        if not self.connected:
            self.logger.warning(f"MQTT broker not connected, cannot publish measurement. Connection status: {self.connected}")
            return False
        
        person_id = measurement.get('person', 0)
        measurement_type = measurement.get('type', 'unknown')
        
        # Create topic based on measurement type and person
        topic = f"{self.mqtt_prefix}/person{person_id}/{measurement_type}"
        self.logger.debug(f"MQTT topic: {topic}")
        
        # Convert timestamp to ISO format if present
        measurement_copy = measurement.copy()  # Create a copy to avoid modifying the original
        if 'timestamp' in measurement_copy and isinstance(measurement_copy['timestamp'], datetime):
            measurement_copy['timestamp'] = measurement_copy['timestamp'].isoformat()
            self.logger.debug(f"Converted timestamp to ISO format: {measurement_copy['timestamp']}")
        
        # Convert to JSON and publish
        try:
            payload = json.dumps(measurement_copy)
            self.logger.debug(f"JSON payload created: {payload}")
        except Exception as e:
            self.logger.error(f"Failed to serialize measurement to JSON: {str(e)}", exc_info=True)
            return False
        
        try:
            self.logger.info(f"Publishing to MQTT topic: {topic}")
            self.logger.debug(f"Publish parameters - QoS: {self.mqtt_qos}, Retain: {self.mqtt_retain}")
            self.logger.debug(f"Payload (first 200 chars): {payload[:200]}")
            
            result = self.client.publish(topic, payload, qos=self.mqtt_qos, retain=self.mqtt_retain)
            
            # Log detailed publish result
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.logger.info(f"Successfully published to {topic} (Message ID: {result.mid})")
                self.logger.debug(f"Publish result - rc: {result.rc}, mid: {result.mid}, is_published: {result.is_published()}")
                return True
            else:
                error_messages = {
                    mqtt.MQTT_ERR_NO_CONN: "No connection to broker",
                    mqtt.MQTT_ERR_QUEUE_SIZE: "Message queue is full"
                }
                error_msg = error_messages.get(result.rc, f"Unknown error code: {result.rc}")
                self.logger.error(f"Failed to publish to {topic}: {error_msg} (Error code: {result.rc})")
                return False
                
        except Exception as e:
            self.logger.error(f"Exception while publishing to MQTT: {str(e)}", exc_info=True)
            return False
    
    def process_measurements(self, measurements):
        """Process multiple measurements and publish only the most recent per person per type for the person who just stepped on."""
        # Reset tracking for this batch
        self.most_recent = {}
        current_person_id = None
        
        # First pass: find the most recent "person" measurement to identify who just stepped on
        # Since person measurements don't have timestamps, we use the last one in the list
        # (measurements are received in order, so the last person measurement is the current one)
        self.logger.info(f"Processing {len(measurements)} measurements to identify current person")
        most_recent_person_measurement = None
        
        # Find the last person measurement (most recent)
        for measurement in reversed(measurements):
            if measurement.get('type') == 'person':
                most_recent_person_measurement = measurement
                break
        
        if most_recent_person_measurement:
            current_person_id = most_recent_person_measurement.get('person')
            self.logger.info(f"Identified current person from scale: ID {current_person_id}")
        else:
            self.logger.warning("No person measurement found, cannot identify who stepped on the scale")
            return
        
        # Second pass: track measurements only for the current person
        self.logger.info(f"Finding most recent measurements for person {current_person_id}")
        for measurement in measurements:
            # Only process measurements for the current person
            if measurement.get('person') == current_person_id:
                self.process_measurement(measurement)
        
        # Third pass: publish only the most recent measurements for the current person
        if not self.most_recent:
            self.logger.warning(f"No valid measurements found for person {current_person_id}")
            return
        
        self.logger.info(f"Publishing {len(self.most_recent)} most recent measurement(s) for person {current_person_id} to MQTT")
        published_count = 0
        for key, measurement in self.most_recent.items():
            person_id, measurement_type = key
            if person_id == current_person_id:  # Double-check (should always be true)
                self.logger.debug(f"Publishing most recent {measurement_type} for person {person_id}")
                if self._publish_measurement(measurement):
                    published_count += 1
        
        self.logger.info(f"Successfully published {published_count} out of {len(self.most_recent)} most recent measurement(s) for person {current_person_id}") 
