# can_interface.py
import can
import threading
import logging
from config import Config
from data_manager import DataManager

logger = logging.getLogger("RobotApp")


class CanInterface:
    """
    Class that wraps the CAN bus connection.
    It handles opening, closing, and gives access to the bus
    for sending/receiving messages.
    
    Uses a DataManager for thread-safe centralized state management.
    """

    def __init__(self, config: Config, data_manager: DataManager):
        """
        Initialize CAN interface with configuration and data manager.

        Args:
            config (Config): Configuration object containing CAN settings and motor IDs
            data_manager (DataManager): Centralized thread-safe data store
        """
        self.config = config
        self.data_manager = data_manager
        self.channel = config.can.channel
        self.bustype = config.can.bustype
        self.bitrate = config.can.bitrate
        self.recv_timeout = config.can.recv_timeout
        self.no_listener_timeout = config.can.no_listener_timeout
        self.bus = None

        # Threading control for the background listener
        self._listener_thread = None
        self._stop_event = threading.Event()

        motor_ids = config.get_motor_ids()
        logger.debug("CanInterface initialized with channel=%s, bustype=%s, bitrate=%d, %d motors",
                     self.channel, self.bustype, self.bitrate, len(motor_ids))

    def connect(self):
        """Opens the connection to the CAN bus."""
        try:
            self.bus = can.interface.Bus(
                channel=self.channel,
                bustype=self.bustype
            )
            logger.info("CAN connection established on %s (%s) at %d bps",
                        self.channel, self.bustype, self.bitrate)
        except can.CanError as e:
            logger.error("Failed to establish CAN connection on %s: %s",
                         self.channel, str(e))
            raise

    def disconnect(self):
        """Properly closes the connection."""
        self.stop_listening()
        if self.bus is not None:
            try:
                self.bus.shutdown()
                logger.info("CAN connection closed on %s", self.channel)
            except Exception as e:
                logger.error("Error while closing CAN connection: %s", str(e))

    def calculate_checksum(self, motor_id, command_bytes):
        """
        Calculate the checksum by summing the motor ID and all command bytes.
        Only the last 2 hexadecimal digits of the result are kept (modulo 256).

        Args:
            motor_id (int): Motor ID (e.g., 0x01)
            command_bytes (list): List of command bytes (e.g., [0xF6, 0x01, 0x2C, 0x02])

        Returns:
            int: The calculated checksum (0 to 255)
        """
        total = motor_id + sum(command_bytes)
        checksum = total % 256  # keep only the last byte (last 2 hex digits)
        logger.debug("Checksum calculated: motor_id=0x%02X, command_bytes=%s, checksum=0x%02X",
                     motor_id, command_bytes, checksum)
        return checksum

    def send_command(self, motor_id, command_bytes):
        """
        Builds and sends a full CAN command: motor_id + command_bytes + checksum.
        Stores the raw TX frame in DataManager for later echo detection on RX.

        Args:
            motor_id (int): The motor ID, used as arbitration_id (e.g. 0x01)
            command_bytes (list): List of command bytes (e.g. [0xF6, 0x01, 0x2C, 0x02])
        """
        if self.bus is None:
            logger.error("Cannot send command to motor 0x%02X: CAN bus not connected",
                         motor_id)
            return

        if motor_id not in self.data_manager.motors:
            logger.error("Motor 0x%02X not in registered motors list, command not sent",
                         motor_id)
            return

        checksum = self.calculate_checksum(motor_id, command_bytes)
        data = command_bytes + [checksum]

        message = can.Message(
            arbitration_id=motor_id,
            data=data,
            is_extended_id=False
        )
        try:
            self.bus.send(message)
            logger.debug("Command sent to motor 0x%02X: data=%s, checksum=0x%02X",
                         motor_id, data[:-1], checksum)
        except can.CanError as e:
            logger.error("Error while sending command to motor 0x%02X: %s",
                         motor_id, str(e))
            return

        # Store raw TX frame in DataManager for echo detection on RX
        self.data_manager.update_tx_frame(motor_id, bytes(data))

    # Dans can_interface.py, modifie la méthode receive_command()

    def receive_command(self, message):
        """
        Store the latest received CAN command in the motor's buffer.

        Before storing, the raw data is compared against the last frame we sent
        (last_tx_raw). If identical, the frame is considered a TX echo (bus loopback)
        and is discarded entirely (not even stored as last_rx_raw), so the parser
        never processes our own sent commands.

        The command byte (first byte) and checksum (last byte) are removed before
        storing the data separately.

        Parse and results are automatically stored in DataManager.

        Args:
            message (can.Message): A CAN message instance received from the bus
            parse_and_store (bool): if True, parse and store in DataManager
        """
        motor_id = message.arbitration_id

        if motor_id not in self.data_manager.motors:
            logger.error("Motor 0x%02X not in registered motors", motor_id)
            return

        raw_data = bytes(message.data)

        # TX echo detection
        last_tx = self.data_manager.get_tx_frame(motor_id)
        if last_tx is not None and raw_data == last_tx:
            logger.debug("TX echo detected for motor 0x%02X, skipping", motor_id)
            return

        old_rx = self.data_manager.get_old_rx_frame(motor_id)
        if old_rx is not None and raw_data == old_rx:
            logger.debug("Duplicate frame detected for motor 0x%02X, skipping", motor_id)
            return

        # Extract command byte and payload
        command_byte = raw_data[0]
        payload = raw_data[1:-1]  # Remove command byte and checksum

        if len(payload) == 0:
            logger.warning("CAN command from motor 0x%02X has no data after removing command/checksum",
                        motor_id)
            return

        # Store in DataManager
        self.data_manager.update_rx_frame(motor_id, raw_data, command_byte, payload)

        logger.debug("Frame stored: motor_id=0x%02X, command_byte=0x%02X, data=%s",
                    motor_id, command_byte, payload.hex())

        # Parse and store results if enabled
        from parser import parse_motor_frame
        parse_motor_frame(motor_id, command_byte, payload, self.config, self.data_manager)

    def _listen(self):
        """Background listener thread that continuously receives CAN messages."""
        logger.debug("CAN listener thread started on %s", self.channel)
        while not self._stop_event.is_set():
            try:
                message = self.bus.recv(timeout=self.recv_timeout)
                if message is not None:
                    self.receive_command(message)
            except can.CanError as e:
                logger.warning("Error in CAN listener thread: %s", str(e))
            except Exception as e:
                logger.error("Unexpected error in CAN listener thread: %s", str(e))

    def start_listening(self):
        """Starts the background listener thread."""
        if self._listener_thread is not None and self._listener_thread.is_alive():
            logger.warning("Listener thread already running")
            return

        self._stop_event.clear()
        self._listener_thread = threading.Thread(target=self._listen, daemon=True)
        self._listener_thread.start()
        logger.info("CAN listener thread started on %s", self.channel)

    def stop_listening(self):
        """Stops the background listener thread cleanly."""
        if self._listener_thread is not None:
            self._stop_event.set()
            self._listener_thread.join(timeout=self.no_listener_timeout)
            logger.info("CAN listener thread stopped")
        else:
            logger.debug("No listener thread to stop")