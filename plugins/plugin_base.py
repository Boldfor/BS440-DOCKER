class PluginBase:
    """Base class for all plugins."""
    
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.name = self.__class__.__name__
        self.logger.info(f"Initializing plugin: {self.name}")
        
    def process_measurement(self, measurement):
        """Process a single measurement."""
        raise NotImplementedError("Each plugin must implement process_measurement")
        
    def process_measurements(self, measurements):
        """Process multiple measurements."""
        for measurement in measurements:
            self.process_measurement(measurement) 