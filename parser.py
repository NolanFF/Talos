# parser.py
import logging
from config import Config
from data_manager import DataManager

logger = logging.getLogger("RobotApp")


def parse_command_31(data: bytes, config: Config) -> dict:
    """
    Parse command 0x31: encoder position feedback.

    Frame data format:
        - N bytes (see config.parser.response_lengths[0x31]), big-endian, unsigned integer
        - represents encoder position in raw counts

    Args:
        data (bytes): raw payload bytes for this command (already length-checked)
        config (Config): app config (unused here, kept for signature consistency)

    Returns:
        dict: {"position": int}
    """
    # Unsigned big-endian conversion: no negative position possible
    position = int.from_bytes(data, byteorder="big", signed=False)

    logger.debug("Parsed encoder position: %d", position)

    return {"position": position}

def parse_command_3D(data: bytes, config: Config) -> dict:
    """
    Parse command 0x3D: encoder position feedback.

    Frame data format:
        - N bytes (see config.parser.response_lengths[0x31]), big-endian, unsigned integer
        - represents encoder position in raw counts

    Args:
        data (bytes): raw payload bytes for this command (already length-checked)
        config (Config): app config (unused here, kept for signature consistency)

    Returns:
        dict: {"position": int}
    """
    # Unsigned big-endian conversion: no negative position possible
    position = int.from_bytes(data, byteorder="big", signed=False)

    logger.debug("Parsed encoder position: %d", position)

    return {"position": position}


# Command byte constants (add more as we implement them)
CMD_ENCODER_POSITION = 0x31
CMD_LIBERATION_MOTEUR = 0x3D

# Registry mapping command byte -> parser function
# Each parser function must have signature: (data: bytes, config: Config) -> dict
COMMAND_PARSERS = {
    CMD_ENCODER_POSITION: parse_command_31,
    CMD_LIBERATION_MOTEUR: parse_command_3D,
}


def parse_motor_frame(motor_id: int, command_byte: int, data: bytes, 
                      config: Config, data_manager: DataManager = None) -> dict:
    """
    Dispatch a single motor's frame data to the correct parser
    based on the command byte, after validating the expected length
    from config.parser.response_lengths.

    If data_manager is provided, the parsed results are automatically
    stored in the motor's state (e.g., encoder_value, io_states, etc.).

    Args:
        motor_id (int): motor ID (for logging context)
        command_byte (int): command type byte from the frame
        data (bytes): payload data to parse
        config (Config): app config, used to fetch expected length and forwarded to the parser
        data_manager (DataManager, optional): if provided, stores parsed data in motor state

    Returns:
        dict: parsed result, or empty dict if no parser matches or length mismatch
    """
    parser_func = COMMAND_PARSERS.get(command_byte)

    if parser_func is None:
        logger.debug(
            "No parser registered for command 0x%02X (motor 0x%02X)",
            command_byte, motor_id
        )
        return {}

    expected_length = config.parser.response_lengths.get(command_byte)

    if expected_length is None:
        logger.warning(
            "No expected length configured for command 0x%02X (motor 0x%02X)",
            command_byte, motor_id
        )
        return {}

    if len(data) != expected_length:
        logger.warning(
            "Invalid data length for command 0x%02X (motor 0x%02X): expected %d, got %d",
            command_byte, motor_id, expected_length, len(data)
        )
        return {}

    # Parse the frame
    parsed_result = parser_func(data, config)

    # If DataManager provided, store the parsed results
    if data_manager is not None and parsed_result:
        _store_parsed_results(motor_id, command_byte, parsed_result, data_manager)

    return parsed_result


def _store_parsed_results(motor_id: int, command_byte: int, 
                          parsed_result: dict, data_manager: DataManager):
    """
    Store parsed results into DataManager based on command byte.

    This function maps parsed data to the appropriate motor state fields
    (encoder_value, io_states, analog_values, etc.).

    Args:
        motor_id (int): motor ID
        command_byte (int): command type (determines what to store)
        parsed_result (dict): result dict from parser function
        data_manager (DataManager): manager instance
    """
    if command_byte == CMD_ENCODER_POSITION:
        # Store encoder position
        position = parsed_result.get("position")
        if position is not None:
            data_manager.set_encoder_value(motor_id, position)
            logger.debug("Stored encoder position for motor 0x%02X: %d", motor_id, position)

    # Add more command handlers here as parsers are implemented
    # Example:
    # elif command_byte == CMD_IO_STATUS:
    #     io_states = parsed_result.get("io_states")
    #     if io_states:
    #         data_manager.set_io_state(motor_id, "ready", io_states.get("ready", False))
    #         data_manager.set_io_state(motor_id, "error", io_states.get("error", False))