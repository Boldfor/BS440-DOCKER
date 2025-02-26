from datetime import datetime, timedelta
import struct
import sys

class MedisanaBS440:
    def __init__(self, logger):
        self.logger = logger
        
    def parse_measurement(self, data):
        """Parse measurement data from BS440 scale"""
        measurement = {}
        
        # Convert bytes to hex string for logging
        hex_data = data.hex()
        self.logger.debug(f"Parsing measurement data: {hex_data}")
        
        try:
            message_type = data[0]
            
            if message_type == 0x84:  # Person data
                # Format: BxBxBBBxB
                # B = type (0x84), x = pad, B = person, x = pad, B = gender, B = age, B = size, x = pad, B = activity
                measurement['type'] = 'person'
                # First byte should be 0x84 for validity
                if data[0] != 0x84:
                    return None
                measurement['person'] = data[2]
                measurement['gender'] = 'male' if data[4] == 1 else 'female'
                measurement['age'] = data[5]
                measurement['size'] = data[6]  # Height in cm
                measurement['activity'] = 'high' if data[8] == 3 else 'normal'
                
            elif message_type == 0x1D:  # Weight data
                # Format: BHxxIxxxxB
                # B = type (0x1D), H = weight (LSB), xx = pad, 
                # I = timestamp, xxxx = pad, B = person
                measurement['type'] = 'weight'
                
                # First byte should be 0x1D for validity
                if data[0] != 0x1D:
                    return None
                
                # Weight is 2 bytes, little endian, in 10g units
                weight = struct.unpack('<H', data[1:3])[0]
                weight_kg = weight / 100.0  # Convert to kg
                measurement['weight'] = weight_kg
                
                # Stability (bit 0), impedance measured (bit 1)
                measurement['stabilized'] = bool(data[3] & 0x01)  
                measurement['impedance_measured'] = bool(data[3] & 0x02)
                
                # Get raw timestamp from data
                raw_timestamp = struct.unpack('<I', data[5:9])[0]
                
                # Log raw timestamp and hex representation for debugging
                self.logger.debug(f"Weight raw timestamp: {raw_timestamp} (0x{raw_timestamp:08x})")
                
                # Apply time offset from original BS440.py code
                # On BS410/BS444 time=0 equals 1/1/2010 (timestamp 1262304000)
                time_offset = 1262304000  # 2010-01-01 in Unix timestamp
                
                # Apply sanitization logic from original code
                if raw_timestamp + time_offset < sys.maxsize:
                    unix_timestamp = raw_timestamp + time_offset
                    self.logger.debug(f"Using timestamp with offset: {unix_timestamp}")
                else:
                    unix_timestamp = raw_timestamp
                    self.logger.debug(f"Using raw timestamp: {unix_timestamp}")
                
                # If timestamp is still too large, use 0
                if raw_timestamp >= sys.maxsize:
                    unix_timestamp = 0
                    self.logger.debug("Timestamp too large, using 0")
                
                # Convert to datetime
                try:
                    measurement['timestamp'] = datetime.fromtimestamp(unix_timestamp)
                    self.logger.debug(f"Final timestamp: {measurement['timestamp']}")
                except (ValueError, OSError, OverflowError) as e:
                    self.logger.error(f"Error converting timestamp: {e}")
                    # Fallback to current time
                    measurement['timestamp'] = datetime.now()
                    self.logger.debug(f"Using current time instead: {measurement['timestamp']}")
                
                measurement['person'] = data[13]  # Person ID at offset 13 as in original
                
            elif message_type == 0x6F:  # Body composition data
                # Format: BIBHHHHH
                # B = type (0x6F), I = timestamp, B = person, H = kcal, H = fat%, H = water%, H = muscle%, H = bone%
                measurement['type'] = 'body'
                
                # First byte should be 0x6F for validity
                if data[0] != 0x6F:
                    return None
                
                # Get raw timestamp from data
                raw_timestamp = struct.unpack('<I', data[1:5])[0]
                
                # Log raw timestamp and hex representation for debugging
                self.logger.debug(f"Body raw timestamp: {raw_timestamp} (0x{raw_timestamp:08x})")
                
                # Apply sanitize_timestamp logic from original BS440.py
                time_offset = 1262304000  # 2010-01-01 in Unix timestamp
                max_timestamp = sys.maxsize
                
                # Detailed logging of timestamp processing
                self.logger.debug(f"Time offset: {time_offset}")
                self.logger.debug(f"Max timestamp: {max_timestamp}")
                self.logger.debug(f"Raw + offset: {raw_timestamp + time_offset}")
                
                # Apply sanitization logic from original code
                if raw_timestamp + time_offset < max_timestamp:
                    unix_timestamp = raw_timestamp + time_offset
                    self.logger.debug(f"Using sanitized timestamp: {unix_timestamp}")
                else:
                    unix_timestamp = raw_timestamp
                    self.logger.debug(f"Using raw timestamp: {unix_timestamp}")
                    
                # If timestamp is still too large, use 0
                if raw_timestamp >= max_timestamp:
                    unix_timestamp = 0
                    self.logger.debug("Timestamp too large, using 0")
                
                # Convert to datetime
                try:
                    measurement['timestamp'] = datetime.fromtimestamp(unix_timestamp)
                    self.logger.debug(f"Final timestamp: {measurement['timestamp']}")
                except (ValueError, OSError, OverflowError) as e:
                    self.logger.error(f"Error converting timestamp: {e}")
                    # Fallback to current time
                    measurement['timestamp'] = datetime.now()
                    self.logger.debug(f"Using current time instead: {measurement['timestamp']}")
                
                measurement['person'] = data[5]
                
                # Unpack all measurements at once
                kcal, fat, water, muscle, bone = struct.unpack('<HHHHH', data[6:16])
                
                measurement['kcal'] = kcal
                # Fat, water, muscle and bone need to mask first nibble (0xf) and divide by 10
                measurement['fat'] = (0x0FFF & fat) / 10.0
                measurement['tbw'] = (0x0FFF & water) / 10.0  # Total Body Water
                measurement['muscle'] = (0x0FFF & muscle) / 10.0
                measurement['bone'] = (0x0FFF & bone) / 10.0
                
            else:
                self.logger.debug(f"Unknown message type: 0x{message_type:02x}")
                return None
                
            return measurement
            
        except Exception as e:
            self.logger.error(f"Error parsing measurement data: {str(e)}")
            return None
            
    def _parse_timestamp(self, data):
        """Parse timestamp from BS440 data"""
        try:
            # The timestamp format appears to be:
            # Byte 0: Year offset from 2000
            # Byte 1: Month (1-12)
            # Byte 2: Day (1-31)
            # Byte 3: Hour (0-23)
            # Byte 4: Minute (0-59)
            # Byte 5: Second (0-59)
            
            year = 2000 + data[0]
            month = data[1]
            day = data[2]
            hour = data[3]
            minute = data[4]
            second = data[5]
            
            # Add validation
            if not (1 <= month <= 12):
                self.logger.warning(f"Invalid month: {month}, using 1")
                month = 1
            if not (1 <= day <= 31):
                self.logger.warning(f"Invalid day: {day}, using 1")
                day = 1
            if not (0 <= hour <= 23):
                self.logger.warning(f"Invalid hour: {hour}, using 0")
                hour = 0
            if not (0 <= minute <= 59):
                self.logger.warning(f"Invalid minute: {minute}, using 0")
                minute = 0
            if not (0 <= second <= 59):
                self.logger.warning(f"Invalid second: {second}, using 0")
                second = 0
            
            return datetime(year, month, day, hour, minute, second)
            
        except Exception as e:
            self.logger.error(f"Error parsing timestamp: {str(e)}")
            return None
