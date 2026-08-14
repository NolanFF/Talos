import threading
import time
from typing import Dict, Any, List

def parse_0x31(frame_data: bytes) -> int:
    """
    Parse encoder value from 0x31 command frame.
    
    Takes the first 2 bytes (big-endian) and converts to decimal.
    
    Args:
        frame_data (bytes): The 6 useful data bytes from the CAN message
        
    Returns:
        int: Encoder value in decimal
        
    Example:
        [0x00, 0x00, 0x00, 0x01, 0xA9, 0x2E] → 108846
    """
    # Take first 2 bytes, big-endian conversion
    encoder_value = int.from_bytes(frame_data[0:2], byteorder='big')
    return encoder_value


def has_frame_changed(current: List[int], previous: List[int]) -> bool:
    """
    Compare current frame with previous frame.
    
    Args:
        current (List[int]): Current frame bytes
        previous (List[int]): Previous frame bytes (None if first reception)
        
    Returns:
        bool: True if frames are different or if previous is None
    """
    if previous is None:
        return True
    return current != previous


def monitor_frames(raw_frames_buffer: Dict[str, Dict], stop_event: threading.Event):
    """
    Monitor received frames in a separate thread.
    
    For each robot and command type:
    - Check if current frame differs from previous
    - If yes: parse it and update the robot dictionary
    - Update "previous" with current frame
    
    Args:
        raw_frames_buffer (Dict): The shared frames buffer from can_interface
        stop_event (threading.Event): Thread stop signal
    """
    while not stop_event.is_set():
        try:
            # Iterate over all robots
            for robot_id, robot_data in raw_frames_buffer.items():
                
                # Iterate over all command types for this robot
                for command_byte, frame_info in robot_data.items():
                    
                    current_frame = frame_info.get("current")
                    previous_frame = frame_info.get("previous")
                    
                    # Check if frame has changed
                    if current_frame is not None and has_frame_changed(current_frame, previous_frame):
                        
                        # Route to appropriate parser based on command_byte
                        if command_byte == 0x31:
                            parsed_value = parse_0x31(bytes(current_frame))
                            frame_info["encoder_value"] = parsed_value
                        
                        # Add more parsers here as needed:
                        # elif command_byte == 0x32:
                        #     parsed_value = parse_0x32(bytes(current_frame))
                        #     frame_info["some_field"] = parsed_value
                        
                        # Update previous frame
                        frame_info["previous"] = current_frame.copy()
        
        except Exception as e:
            print(f"[monitor_frames] Error: {e}")
        
        # Small sleep to avoid CPU spinning
        time.sleep(0.01)


def start_monitor_thread(raw_frames_buffer: Dict[str, Dict]) -> threading.Event:
    """
    Start the frame monitor in a background thread.
    
    Args:
        raw_frames_buffer (Dict): The shared frames buffer from can_interface
        
    Returns:
        threading.Event: Stop event to signal thread shutdown
    """
    stop_event = threading.Event()
    monitor_thread = threading.Thread(
        target=monitor_frames,
        args=(raw_frames_buffer, stop_event),
        daemon=False
    )
    monitor_thread.start()
    return stop_event