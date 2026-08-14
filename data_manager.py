# data_manager.py
import threading
from dataclasses import dataclass, field
from typing import Dict, Any
import logging

logger = logging.getLogger("DataManager")


@dataclass
class MotorState:
    """Complete state of a single motor"""
    motor_id: int

    """Can Interface"""
    rx_raw: bytes = None
    old_rx_raw: bytes = None
    has_changed: bool = False
    tx_raw: bytes = None
    rx_command_byte: int = None
    rx_data: bytes = None
    
    """Parser"""
    encoder_value: int = 0
    io_states: Dict[str, bool] = field(default_factory=dict)
    analog_values: Dict[str, float] = field(default_factory=dict)


class DataManager:
    """
    Thread-safe centralized data store for all robot state.
    Single source of truth for motor frames, I/O, encoder values, etc.
    
    Design:
    - Uses RLock (re-entrant lock) for thread-safety
    - All access goes through this manager to avoid race conditions
    - Easy to persist/export later (JSON, socket, DB, etc.)
    """
    
    def __init__(self, motor_ids: list):
        """
        Initialize DataManager with known motor IDs.
        
        Args:
            motor_ids (list): List of motor IDs (e.g., [0x01, 0x02, 0x03])
        """
        self._lock = threading.RLock()
        
        # Initialize all motors with empty state
        self.motors: Dict[int, MotorState] = {
            mid: MotorState(motor_id=mid)
            for mid in motor_ids
        }
        
        logger.info("DataManager initialized with %d motors", len(motor_ids))
    
    # ===== CAN INTERFACE =====
    
    def update_rx_frame(self, motor_id: int, raw_data: bytes, 
                        command_byte: int, payload: bytes):
        """
        Store received CAN frame (called by CanInterface.receive_command).
        
        Args:
            motor_id (int): Motor ID
            raw_data (bytes): Complete frame (command_byte + payload + checksum)
            command_byte (int): First byte of frame
            payload (bytes): Data bytes (without command_byte and checksum)
        """
        with self._lock:
            if motor_id not in self.motors:
                logger.error("Motor 0x%02X not registered in DataManager", motor_id)
                return
            
            motor = self.motors[motor_id]
            motor.has_changed = (raw_data != motor.rx_raw)
            motor.old_rx_raw = motor.rx_raw
            motor.rx_raw = raw_data
            motor.rx_command_byte = command_byte
            motor.rx_data = payload
    
    def update_tx_frame(self, motor_id: int, raw_data: bytes):
        """
        Store sent CAN frame (called by CanInterface.send_command).
        
        Args:
            motor_id (int): Motor ID
            raw_data (bytes): Complete frame sent
        """
        with self._lock:
            if motor_id not in self.motors:
                logger.error("Motor 0x%02X not registered in DataManager", motor_id)
                return
            self.motors[motor_id].tx_raw = raw_data
    
    def get_rx_frame(self, motor_id: int) -> tuple:
        """
        Retrieve last received frame safely.
        
        Returns:
            tuple: (command_byte, payload, has_changed) or (None, None, False) if no frame
        """
        with self._lock:
            if motor_id not in self.motors:
                return None, None, False
            m = self.motors[motor_id]
            return m.rx_command_byte, m.rx_data, m.has_changed
    
    def get_tx_frame(self, motor_id: int) -> bytes:
        """Retrieve last transmitted frame."""
        with self._lock:
            if motor_id not in self.motors:
                return None
            return self.motors[motor_id].tx_raw
    
    def get_old_rx_frame(self, motor_id: int) -> bytes:
        """Retrieve previous received frame (for duplicate detection)."""
        with self._lock:
            if motor_id not in self.motors:
                return None
            return self.motors[motor_id].old_rx_raw
    
    # ===== PARSER VALUES =====
    
    def set_encoder_value(self, motor_id: int, value: int):
        """Store latest encoder reading."""
        with self._lock:
            if motor_id not in self.motors:
                logger.error("Motor 0x%02X not registered", motor_id)
                return
            self.motors[motor_id].encoder_value = value
    
    def get_encoder_value(self, motor_id: int) -> int:
        """Retrieve current encoder value."""
        with self._lock:
            if motor_id not in self.motors:
                return 0
            return self.motors[motor_id].encoder_value
    
    # ===== I/O STATES =====
    
    def set_io_state(self, motor_id: int, io_name: str, state: bool):
        """Update a single I/O digital state."""
        with self._lock:
            if motor_id not in self.motors:
                logger.error("Motor 0x%02X not registered", motor_id)
                return
            self.motors[motor_id].io_states[io_name] = state
    
    def get_io_state(self, motor_id: int, io_name: str) -> bool:
        """Read a single I/O digital state."""
        with self._lock:
            if motor_id not in self.motors:
                return False
            return self.motors[motor_id].io_states.get(io_name, False)
    
    def get_all_io_states(self, motor_id: int) -> Dict[str, bool]:
        """Get all I/O states for a motor (returns a copy)."""
        with self._lock:
            if motor_id not in self.motors:
                return {}
            return dict(self.motors[motor_id].io_states)
    
    # ===== ANALOG VALUES =====
    
    def set_analog_value(self, motor_id: int, analog_name: str, value: float):
        """Update an analog reading."""
        with self._lock:
            if motor_id not in self.motors:
                logger.error("Motor 0x%02X not registered", motor_id)
                return
            self.motors[motor_id].analog_values[analog_name] = value
    
    def get_analog_value(self, motor_id: int, analog_name: str) -> float:
        """Read a single analog value."""
        with self._lock:
            if motor_id not in self.motors:
                return 0.0
            return self.motors[motor_id].analog_values.get(analog_name, 0.0)
    
    def get_all_analog_values(self, motor_id: int) -> Dict[str, float]:
        """Get all analog values for a motor (returns a copy)."""
        with self._lock:
            if motor_id not in self.motors:
                return {}
            return dict(self.motors[motor_id].analog_values)
    
    # ===== SNAPSHOT / EXPORT =====
    
    def get_motor_snapshot(self, motor_id: int) -> Dict[str, Any]:
        """
        Get complete state of one motor (useful for export/logging).
        Returns a deep copy to avoid external modifications.
        """
        with self._lock:
            if motor_id not in self.motors:
                return {}
            m = self.motors[motor_id]
            return {
                "motor_id": f"0x{m.motor_id:02X}",
                "rx_raw": m.rx_raw.hex() if m.rx_raw else None,
                "x_command_byte": f"0x{m.rx_command_byte:02X}" if m.rx_command_byte else None,
                "rx_data": m.rx_data.hex() if m.rx_data else None,
                "encoder_value": m.encoder_value,
                "io_states": dict(m.io_states),
                "analog_values": dict(m.analog_values),
                "has_changed": m.has_changed,
            }
    
    def get_all_motors_snapshot(self) -> Dict[int, Dict[str, Any]]:
        """Get complete state of all motors."""
        with self._lock:
            return {
                mid: self.get_motor_snapshot(mid)
                for mid in self.motors.keys()
            }