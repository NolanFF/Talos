# main.py
import logging
from config import Config
from logs.logger import setup_logger
from data_manager import DataManager
from can_interface import CanInterface

# Initialize logger first
logger = setup_logger()


def print_buffer(data_manager, config):
    """Display the current motor states from DataManager in a readable format."""
    motor_ids = config.get_motor_ids()
    
    if not motor_ids:
        print("\n[Buffer] No motors configured\n")
        return

    print("\n[Raw Frames Buffer - DataManager]")
    for motor_id in motor_ids:
        # Get motor name from config
        try:
            motor = config.get_motor(motor_id)
            motor_name = motor.name
        except KeyError:
            motor_name = "Unknown"

        # Get snapshot from DataManager (thread-safe)
        snapshot = data_manager.get_motor_snapshot(motor_id)

        print(f"  Motor 0x{motor_id:02X} ({motor_name}):")

        tx_raw = snapshot.get("tx_raw")
        rx_raw = snapshot.get("rx_raw")
        old_rx_raw = snapshot.get("old_rx_raw")
        has_changed = snapshot.get("has_changed")
        rx_command_byte = snapshot.get("rx_command_byte")
        rx_data = snapshot.get("rx_data")
        encoder_value = snapshot.get("encoder_value")
        io_states = snapshot.get("io_states")
        analog_values = snapshot.get("analog_values")

        tx_hex = tx_raw if tx_raw is not None else "None"
        rx_hex = rx_raw if rx_raw is not None else "None"
        orx_hex = old_rx_raw if old_rx_raw is not None else "None"
        data_hex = rx_data if rx_data is not None else "None"
        command_byte_str = rx_command_byte if rx_command_byte is not None else "None"

        print(f"    TX raw:          {tx_hex}")
        print(f"    RX raw:          {rx_hex}")
        print(f"    Old RX raw:      {orx_hex}")
        print(f"    Has Changed:     {has_changed}")
        print(f"    RX command byte: {command_byte_str}")
        print(f"    RX data:         {data_hex}")
        print(f"    Encoder value:   {encoder_value}")
    print()


def send_command_interactive(can_iface, config):
    """Prompt user to enter motor_id and command_bytes, then send."""
    try:
        motor_id_str = input("Enter motor ID (hex, e.g., 01): ").strip()
        motor_id = int(motor_id_str, 16)

        # Validate motor ID exists in config
        try:
            motor = config.get_motor(motor_id)
            logger.debug("Motor found in config: %s", motor.name)
        except KeyError:
            logger.warning("Motor ID 0x%02X not found in config", motor_id)
            print(f"✗ Error: Motor ID 0x{motor_id:02X} not found in config.\n")
            return

        command_str = input("Enter command bytes (hex, space-separated, e.g., F6 01 2C 02): ").strip()
        command_bytes = [int(b, 16) for b in command_str.split()]

        logger.debug("User input: motor_id=0x%02X (%s), command_bytes=%s",
                     motor_id, motor.name, [f"0x{b:02X}" for b in command_bytes])

        can_iface.send_command(motor_id, command_bytes)
        print("✓ Command sent successfully\n")

    except ValueError as e:
        logger.error("Invalid input format: %s", str(e))
        print("✗ Error: Invalid hex format. Try again.\n")
    except Exception as e:
        logger.error("Error sending command: %s", str(e))
        print(f"✗ Error: {str(e)}\n")


def main():
    """Main interactive loop."""
    logger.info("=== Robot CAN Interface Starting ===")
    can_iface = None

    try:
        # Load configuration
        config = Config()
        logger.info("Configuration loaded: %s", config)

        # Initialize DataManager with motor IDs from config
        data_manager = DataManager(config.get_motor_ids())
        logger.info("DataManager initialized")

        # Create CAN interface with config and data_manager
        can_iface = CanInterface(config, data_manager)

        # Connect to CAN bus
        can_iface.connect()
        logger.info("Connected to CAN bus")

        # Start background listener
        can_iface.start_listening()
        logger.info("Background listener started")

        print("\n" + "="*50)
        print("  Robot CAN Interface - Interactive Console")
        print("="*50)
        print(f"CAN Channel: {config.can.channel}")
        print(f"Motors configured: {len(config.get_motor_ids())}")
        print("\nCommands:")
        print("  send    - Send a command via CAN")
        print("  show    - Show received frames buffer")
        print("  motors  - List all configured motors")
        print("  quit    - Exit the application")
        print("="*50 + "\n")

        # Main loop
        while True:
            try:
                user_input = input(">>> ").strip().lower()

                if user_input == "send":
                    send_command_interactive(can_iface, config)

                elif user_input == "show":
                    print_buffer(data_manager, config)

                elif user_input == "motors":
                    print("\n[Configured Motors]")
                    for motor_id in config.get_motor_ids():
                        motor = config.get_motor(motor_id)
                        print(f"  0x{motor_id:02X}: {motor.name} "
                              f"[{motor.limit_negative:+d}, {motor.limit_positive:+d}]")
                    print()

                elif user_input == "quit":
                    logger.info("User requested exit")
                    print("\nGoodbye!")
                    break

                elif user_input == "":
                    continue

                else:
                    print("Unknown command. Type 'send', 'show', 'motors', or 'quit'.\n")
                    logger.warning("Unknown command entered: %s", user_input)

            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received")
                print("\n\nInterrupted by user")
                break
            except Exception as e:
                logger.error("Unexpected error in main loop: %s", str(e))
                print(f"Error: {str(e)}\n")

    except FileNotFoundError as e:
        logger.critical("Configuration file not found: %s", str(e))
        print(f"Critical error: Config file not found - {str(e)}")
        return 1
    except ValueError as e:
        logger.critical("Invalid configuration: %s", str(e))
        print(f"Critical error: Invalid configuration - {str(e)}")
        return 1
    except Exception as e:
        logger.critical("Failed to initialize CAN interface: %s", str(e))
        print(f"Critical error: {str(e)}")
        return 1

    finally:
        logger.info("Cleaning up...")
        if can_iface is not None:
            can_iface.disconnect()
        logger.info("=== Robot CAN Interface Stopped ===")


if __name__ == "__main__":
    exit(main() or 0)