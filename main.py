import logging
from config import Config
from logs.logger import setup_logger
from can_interface import CanInterface

# Initialize logger first
logger = setup_logger()

def print_buffer(can_iface):
    """Display the current raw_frames_buffer in a readable format."""
    if not can_iface.raw_frames_buffer:
        print("\n[Buffer] Empty\n")
        return

    print("\n[Raw Frames Buffer]")
    for motor_id, buffer in can_iface.raw_frames_buffer.items():
        # Get motor name from config
        try:
            motor = can_iface.config.get_motor(motor_id)
            motor_name = motor.name
        except KeyError:
            motor_name = "Unknown"

        print(f"  Motor 0x{motor_id:02X} ({motor_name}):")

        last_tx_raw = buffer.get("last_tx_raw")
        last_rx_raw = buffer.get("last_rx_raw")
        old_rx_raw = buffer.get("old_rx_raw")
        last_rx_command_byte = buffer.get("last_rx_command_byte")
        last_rx_data = buffer.get("last_rx_data")

        tx_hex = last_tx_raw.hex(" ").upper() if last_tx_raw is not None else "None"
        rx_hex = last_rx_raw.hex(" ").upper() if last_rx_raw is not None else "None"
        orx_hex = old_rx_raw.hex(" ").upper() if old_rx_raw is not None else "None"
        data_hex = last_rx_data.hex(" ").upper() if last_rx_data is not None else "None"
        command_byte_str = f"0x{last_rx_command_byte:02X}" if last_rx_command_byte is not None else "None"

        print(f"    Last TX raw:          {tx_hex}")
        print(f"    Last RX raw:          {rx_hex}")
        print(f"    Old  RX raw:          {orx_hex}")
        print(f"    Last RX command byte: {command_byte_str}")
        print(f"    Last RX data:         {data_hex}")
    print()

def send_command_interactive(can_iface):
    """Prompt user to enter motor_id and command_bytes, then send."""
    try:
        motor_id_str = input("Enter motor ID (hex, e.g., 01): ").strip()
        motor_id = int(motor_id_str, 16)

        # Validate motor ID exists in config
        try:
            motor = can_iface.config.get_motor(motor_id)
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

    try:
        # Load configuration
        config = Config()
        logger.info("Configuration loaded: %s", config)

        # Create CAN interface with config
        can_iface = CanInterface(config)

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
                    send_command_interactive(can_iface)

                elif user_input == "show":
                    print_buffer(can_iface)

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
        can_iface.disconnect()
        logger.info("=== Robot CAN Interface Stopped ===")

if __name__ == "__main__":
    exit(main() or 0)