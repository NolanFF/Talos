import json
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Callable

logger = logging.getLogger("RobotApp")

@dataclass
class CanConfig:
    """CAN bus configuration."""
    channel: str = 'can0'
    bustype: str = 'socketcan'
    bitrate: int = 500000
    recv_timeout: float = 0.1
    no_listener_timeout: float = 2.0

@dataclass
class MotorConfig:
    """Individual motor configuration."""
    name: str
    limit_positive: int
    limit_negative: int

@dataclass
class ParserConfig:
    """CAN frame parser configuration."""
    response_lengths: Dict[int, int] = None

    def __post_init__(self):
        # Avoid mutable default argument pitfall (dataclasses forbid dict as default directly)
        if self.response_lengths is None:
            self.response_lengths = {}

class Config:
    """
    Loads and manages application configuration from config.json.
    Uses dataclasses for type safety and clean access.
    """

    def __init__(self, config_file='config/config.json'):
        """
        Load configuration from JSON file.

        Args:
            config_file (str): Path to the config.json file (default: config/config.json)

        Raises:
            FileNotFoundError: If config file doesn't exist
            json.JSONDecodeError: If config file is malformed
            ValueError: If required config sections are missing
        """
        self.config_path = Path(config_file)

        if not self.config_path.exists():
            logger.error("Config file not found: %s", self.config_path)
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            logger.info("Configuration loaded from %s", self.config_path)
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in config file: %s", str(e))
            raise

        # Parse CAN config (with defaults if not in JSON)
        can_data = data.get('can', {})
        self.can = CanConfig(**can_data)
        logger.debug("CAN config: %s", self.can)

        # Parse parser config (with defaults if not in JSON)
        parser_data = data.get('parser', {})
        if 'response_lengths' in parser_data:
            # JSON keys are hex strings like "0x31", convert to int with base 16
            parser_data['response_lengths'] = {
                int(k, 16): v for k, v in parser_data['response_lengths'].items()
            }
        self.parser = ParserConfig(**parser_data)
        logger.debug("Parser config: %s", self.parser)

        # Parse motors config
        motors_data = data.get('motors', {})
        if not motors_data:
            logger.error("No motors defined in config")
            raise ValueError("No motors defined in config")

        self.motors: Dict[int, MotorConfig] = {}
        for motor_id_str, motor_data in motors_data.items():
            try:
                motor_id = int(motor_id_str)
                self.motors[motor_id] = MotorConfig(**motor_data)
            except (ValueError, TypeError) as e:
                logger.error("Invalid motor config for ID %s: %s", motor_id_str, str(e))
                raise

        logger.info("Loaded %d motor(s)", len(self.motors))

    def get_motor_ids(self):
        """Returns list of all motor IDs."""
        return list(self.motors.keys())

    def get_motor(self, motor_id: int) -> MotorConfig:
        """
        Get motor configuration by ID.

        Args:
            motor_id (int): Motor ID

        Returns:
            MotorConfig: Motor configuration object

        Raises:
            KeyError: If motor_id not found
        """
        if motor_id not in self.motors:
            logger.warning("Motor ID %d not found in config", motor_id)
            raise KeyError(f"Motor ID {motor_id} not found in config")

        return self.motors[motor_id]

    def __repr__(self):
        return f"<Config: {self.config_path}, {len(self.motors)} motors>"