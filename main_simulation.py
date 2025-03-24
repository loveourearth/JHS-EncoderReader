#!/usr/bin/env python3
"""
Encoder System OSC Communication Simulator

For testing and development, simulates the OSC communication features of the encoder system
"""
import sys
import os
import time
import argparse
import random
import math
import logging
import signal
from threading import Thread, Event
import json

# Add project root directory to path for correct module imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import OSC related libraries
try:
    from pythonosc import udp_client
    # Direct import to avoid circular dependency
    from pythonosc import dispatcher
    from pythonosc import osc_server
    from pythonosc.osc_message_builder import OscMessageBuilder

    # Import local OSC server implementation if available, with fallback
    try:
        from modbus_encoder.network.osc_server import OSCServer
        print("Using custom OSC server implementation")
    except (ImportError, SyntaxError) as e:
        print(f"Error importing custom OSC server: {e}")
        print("Falling back to basic OSC implementation")

        # Define a simple OSC server wrapper as fallback
        class OSCServer:
            def __init__(self, host="0.0.0.0", port=8888, command_handler=None, return_port=9999):
                self.host = host
                self.port = port
                self.command_handler = command_handler
                self.return_port = return_port
                self.dispatcher = dispatcher.Dispatcher()
                self.clients = {}
                self.clients_lock = threading.RLock()
                self.rx_count = 0
                self.tx_count = 0
                self.error_count = 0
                self.quiet_mode = False  # Add a flag for quiet mode

                # Register handlers
                self.dispatcher.set_default_handler(self._default_handler)

            def _default_handler(self, address, *args):
                print(f"Received OSC message: {address} {args}")
                self.rx_count += 1
                if self.command_handler:
                    if args and isinstance(args[0], str):
                        command = {"command": args[0]}
                        client_address = ("127.0.0.1", self.return_port)
                        result = self.command_handler(command, client_address)
                        if result:
                            self.send_response(result, client_address)

            def start(self):
                try:
                    self.server = osc_server.ThreadingOSCUDPServer(
                        (self.host, self.port), self.dispatcher)
                    self.server_thread = Thread(
                        target=self.server.serve_forever)
                    self.server_thread.daemon = True
                    self.server_thread.start()
                    self.running = True
                    return True
                except Exception as e:
                    print(f"Failed to start OSC server: {e}")
                    return False

            def stop(self):
                if hasattr(self, 'server'):
                    self.server.shutdown()
                self.running = False

            def send_response(self, data, client_address=None, format_type="json"):
                if client_address is None:
                    client_address = ("127.0.0.1", self.return_port)

                try:
                    # Ensure port is correct
                    if isinstance(client_address, tuple) and len(client_address) == 2:
                        client_address = (client_address[0], self.return_port)

                    client = udp_client.SimpleUDPClient(
                        client_address[0], client_address[1])

                    # Convert data to JSON string for sending
                    if isinstance(data, (dict, list)):
                        json_data = json.dumps(data)
                    else:
                        json_data = str(data)

                    # Determine the address
                    address = "/response"
                    if isinstance(data, dict) and "type" in data:
                        if data["type"] == "monitor_data":
                            address = "/encoder/data"

                    # Send the data
                    client.send_message(address, json_data)
                    self.tx_count += 1
                    return True
                except Exception as e:
                    print(f"Error sending response: {e}")
                    self.error_count += 1
                    return False

            def broadcast(self, address, data):
                # Record client info
                with self.clients_lock:
                    client_key = f"127.0.0.1:{self.return_port}"
                    if client_key not in self.clients:
                        self.clients[client_key] = {
                            "address": ("127.0.0.1", self.return_port),
                            "last_seen": time.time()
                        }

                # Only print broadcast message if not in quiet mode
                if not self.quiet_mode:
                    print(f"Broadcasting to 1 clients: {address}")

                # Send to localhost
                self.send_response(data, ("127.0.0.1", self.return_port))
                return 1  # Return count of clients

            def get_statistics(self):
                return {
                    "rx_count": self.rx_count,
                    "tx_count": self.tx_count,
                    "error_count": self.error_count,
                    "active_clients": len(self.clients)
                }

except ImportError:
    print("Please install python-osc library: pip install python-osc")
    sys.exit(1)

# Global variables
running = True
stop_event = Event()
logger = logging.getLogger(__name__)

# Simulation data


class EncoderSimulator:
    def __init__(self):
        self.position = 0.0  # Current angle (0-360)
        self.multi_position = 0.0  # Multi-turn position
        self.speed = 0.0  # Rotation speed (RPM)
        self.direction = 1  # 1=Clockwise, -1=Counter-clockwise
        self.laps = 0  # Number of laps
        self.connected = True  # Connection status
        self.last_update = time.time()
        self.auto_rotate = False
        self.gpio_states = [False] * 8  # 8 GPIO states

    def update(self):
        """Update simulated encoder data"""
        now = time.time()
        dt = now - self.last_update

        if self.auto_rotate:
            # Auto rotation mode
            delta = self.speed * (dt / 60.0) * 360.0  # RPM to degrees/second
            self.position += delta * self.direction

            # Keep angle within 0-360 range and count laps
            if self.position >= 360:
                self.laps += int(self.position / 360)
                self.position %= 360
            elif self.position < 0:
                self.laps -= int(abs(self.position) / 360) + 1
                self.position = 360 - (abs(self.position) % 360)

            self.multi_position = self.position + (self.laps * 360)

        self.last_update = now
        return self.get_data()

    def get_data(self):
        """Get current simulation data"""
        return {
            "address": 1,
            "timestamp": time.time(),
            "position": self.position,
            "multi_position": self.multi_position,
            "direction": self.direction,
            "angle": self.position,
            "rpm": self.speed,
            "laps": self.laps,
            "raw_angle": int(self.position * 1000),
            "raw_rpm": int(self.speed * 1000),
            "connected": self.connected
        }

    def set_position(self, position):
        """Set position"""
        self.position = position % 360
        self.update()

    def set_speed(self, speed):
        """Set speed"""
        self.speed = speed

    def set_direction(self, direction):
        """Set direction"""
        self.direction = direction

    def toggle_rotation(self):
        """Toggle auto rotation state"""
        self.auto_rotate = not self.auto_rotate
        return self.auto_rotate

    def reset(self):
        """Reset simulator"""
        self.position = 0.0
        self.multi_position = 0.0
        self.speed = 0.0
        self.laps = 0

    def toggle_gpio(self, pin):
        """Toggle GPIO state"""
        if 0 <= pin < len(self.gpio_states):
            self.gpio_states[pin] = not self.gpio_states[pin]
            return self.gpio_states[pin]
        return None

# Handle system signals


def signal_handler(sig, frame):
    """Handle system signals (like Ctrl+C)"""
    global running
    print("\nReceived termination signal, shutting down simulator...")
    running = False
    stop_event.set()


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def setup_logging(debug=False):
    """Configure logging system"""
    log_level = logging.DEBUG if debug else logging.INFO

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("simulation.log")
        ]
    )

    logging.getLogger("pythonosc").setLevel(logging.WARNING)


def command_handler(command, client_address):
    """Handle commands received from OSC"""
    logger.debug(f"Processing command: {command} from {client_address}")

    if "command" not in command:
        return {"status": "error", "message": "Invalid command format"}

    cmd = command["command"].lower()

    # Debug output to verify command processing
    print(f"OSC Command received: {cmd} from {client_address}")

    # Force client registration with the OSC server so we can send data back
    if hasattr(osc_server, 'clients_lock') and hasattr(osc_server, 'clients'):
        with osc_server.clients_lock:
            client_key = f"{client_address[0]}:{client_address[1]}"
            if client_key not in osc_server.clients:
                osc_server.clients[client_key] = {
                    "address": client_address,
                    "last_seen": time.time(),
                    "subscribe": ["monitor"],
                    "format": "json"
                }
                print(f"Registered new client: {client_address}")

    # Encoder commands
    if cmd == "connect":
        return {"status": "success", "connected": simulator.connected}
    elif cmd == "disconnect":
        simulator.connected = False
        return {"status": "success", "connected": False}
    elif cmd == "read_position":
        return {
            "status": "success",
            "position": simulator.position,
            "multi_position": simulator.multi_position,
            "angle": simulator.position
        }
    elif cmd == "read_speed":
        return {"status": "success", "rpm": simulator.speed}
    elif cmd == "read_status":
        return {"status": "success", "data": simulator.get_data()}
    elif cmd == "set_zero":
        simulator.position = 0.0
        simulator.laps = 0
        simulator.multi_position = 0.0
        return {
            "status": "success",
            "type": "zero_set",
            "message": "Zero point set successfully"
        }
    elif cmd == "start_monitor":
        # Only return confirmation, actual data sending happens in main loop
        interval = command.get("interval", 0.5)
        format_type = command.get("format", "json")
        return {
            "status": "success",
            "type": "start_monitor",
            "message": f"Started monitoring data, interval {interval} seconds",
            "interval": interval,
            "format": format_type
        }
    elif cmd == "stop_monitor":
        return {
            "status": "success",
            "type": "stop_monitor",
            "message": "Stopped monitoring data"
        }

    # GPIO commands
    elif cmd.startswith("gpio_"):
        action = cmd[5:]  # remove prefix "gpio_"
        pin = command.get("pin", 0)

        if action == "high":
            simulator.gpio_states[pin] = True
            return {"status": "success", "pin": pin, "state": True}
        elif action == "low":
            simulator.gpio_states[pin] = False
            return {"status": "success", "pin": pin, "state": False}
        elif action == "toggle":
            simulator.gpio_states[pin] = not simulator.gpio_states[pin]
            return {"status": "success", "pin": pin, "state": simulator.gpio_states[pin]}
        elif action == "pulse":
            # Pulse feature can be implemented in a separate thread
            duration = command.get("duration", 0.5)
            simulator.gpio_states[pin] = True

            def reset_pin():
                time.sleep(duration)
                simulator.gpio_states[pin] = False

            Thread(target=reset_pin, daemon=True).start()
            return {"status": "success", "pin": pin, "duration": duration}

    elif cmd == "read_input":
        # Return all GPIO states
        return {
            "status": "success",
            "gpio_states": simulator.gpio_states
        }

    # Simulator control commands
    elif cmd == "set_position":
        position = command.get("position", 0.0)
        simulator.set_position(float(position))
        return {"status": "success", "position": simulator.position}
    elif cmd == "set_speed":
        speed = command.get("speed", 0.0)
        simulator.set_speed(float(speed))
        return {"status": "success", "speed": simulator.speed}
    elif cmd == "set_direction":
        direction = command.get("direction", 1)
        simulator.set_direction(int(direction))
        return {"status": "success", "direction": simulator.direction}
    elif cmd == "toggle_rotation":
        auto_rotate = simulator.toggle_rotation()
        return {"status": "success", "auto_rotate": auto_rotate}
    elif cmd == "reset":
        simulator.reset()
        return {"status": "success", "message": "Simulator has been reset"}

    return {"status": "error", "message": f"Unknown command: {cmd}"}


def start_osc_server(host, port, return_port, simulator_instance):
    """Start enhanced OSC server"""
    global simulator
    simulator = simulator_instance

    # Create OSC server
    server = OSCServer(
        host=host,
        port=port,
        command_handler=command_handler,
        return_port=return_port
    )

    # Start server
    success = server.start()
    if success:
        print(
            f"OSC server started, listening at {host}:{port}, return port {return_port}")
    else:
        print(f"OSC server failed to start")
        return None, None

    return server, None  # No separate thread needed, OSCServer class creates its own


def send_periodic_updates(osc_server, simulator, interval=1.0):
    """Periodically send encoder data updates"""
    last_sent = 0

    # Set up a global quiet mode flag that can be checked directly
    global quiet_mode
    quiet_mode = False

    while not stop_event.is_set():
        now = time.time()

        # Update simulator data
        simulator.update()

        # Check if we're in interactive mode and update quiet_mode accordingly
        if hasattr(simulator, 'interactive_mode') and simulator.interactive_mode:
            quiet_mode = True

        # Periodically send data
        if now - last_sent >= interval:
            # Build data
            data = simulator.get_data()
            data["type"] = "monitor_data"

            # Direct test message to localhost:9000 - ensures we're sending something
            try:
                test_client = udp_client.SimpleUDPClient("127.0.0.1", 9000)
                test_client.send_message(
                    "/encoder/direct_test", json.dumps(data))
                if not quiet_mode:
                    print(f"Sending direct test data to 127.0.0.1:9000")
            except Exception as e:
                if not quiet_mode:
                    print(f"Error sending direct test: {e}")

            # Use enhanced OSC server to broadcast data
            try:
                # Modified to directly handle quiet mode
                if hasattr(osc_server, 'send_response'):
                    with osc_server.clients_lock:
                        clients_count = 0
                        for client_key, client in osc_server.clients.items():
                            if osc_server.send_response(data, client["address"]):
                                clients_count += 1

                    # Record sending time
                    last_sent = now

                    # Only print debug info if not in quiet mode
                    if clients_count > 0 and not quiet_mode:
                        print(
                            f"Broadcasting data: pos={data['angle']:.2f}°, speed={data['rpm']:.2f}RPM, laps={data['laps']}, clients={clients_count}")
                else:
                    # Fallback if osc_server doesn't have send_response method
                    clients_count = 0
                    if not quiet_mode:
                        print(
                            f"Warning: OSC server doesn't support expected interface")
            except Exception as e:
                if not quiet_mode:
                    print(f"Error broadcasting data: {e}")
                logger.error(f"Error broadcasting data: {e}")

            # Just log to file in all cases
            logger.debug(
                f"Broadcasting data: pos={data['angle']:.2f}°, speed={data['rpm']:.2f}RPM, laps={data['laps']}")

        # Short sleep to avoid high CPU usage
        time.sleep(0.01)


def print_help():
    """Display help message"""
    print("\n=== OSC Simulator Commands ===")
    print("help            - Display this help message")
    print("quit/exit       - Exit the simulator")
    print("status          - Display current status")
    print("pos VALUE       - Set position (0-360)")
    print("speed VALUE     - Set speed (RPM)")
    print("dir VALUE       - Set direction (1=CW, -1=CCW)")
    print("toggle          - Toggle auto-rotation")
    print("zero            - Set zero point")
    print("gpio PIN STATE  - Set GPIO state (PIN=0-7, STATE=0|1)")
    print("interval VALUE  - Set data sending interval (seconds)")
    print("clients         - Show currently connected clients")
    print("send            - Send a test message to OSC clients")
    print("\n=== Simulator Status ===")


def interactive_mode(simulator, osc_server, interval):
    """Interactive command-line mode"""
    global running, quiet_mode

    print("\n===== Encoder OSC Simulator (Interactive Mode) =====")
    print("Enter 'help' for command list, 'exit' to quit")

    # Set flags to indicate we're in interactive mode
    simulator.interactive_mode = True
    quiet_mode = True

    # Also set the quiet_mode in OSC server if available
    if hasattr(osc_server, 'quiet_mode'):
        osc_server.quiet_mode = True

    current_interval = interval

    # Clear the console for a fresh start
    os.system('cls' if os.name == 'nt' else 'clear')

    # Print a welcome message after clearing
    print("\n===== Encoder OSC Simulator (Interactive Mode) =====")
    print("Enter 'help' for command list, 'exit' to quit")

    while running:
        try:
            # Get command
            cmd = input("\n> ").strip()

            if not cmd:
                continue

            cmd_parts = cmd.lower().split()
            command = cmd_parts[0]

            if command in ["exit", "quit"]:
                running = False
                print("Exiting...")
                break
            elif command == "help":
                print_help()
            elif command == "status":
                data = simulator.get_data()
                print(f"Position: {data['angle']:.2f}°")
                print(f"Multi-turn Position: {data['multi_position']:.2f}°")
                print(f"Speed: {data['rpm']:.2f} RPM")

                direction_text = "Clockwise (CW)" if data['direction'] > 0 else "Counter-clockwise (CCW)"
                print(f"Direction: {direction_text}")

                print(f"Laps: {data['laps']}")

                auto_rotate_text = "ON" if simulator.auto_rotate else "OFF"
                print(f"Auto-rotate: {auto_rotate_text}")

                print(f"GPIO States: {simulator.gpio_states}")
                print(f"Data sending interval: {current_interval:.2f} seconds")

                # Added: Show OSC statistics
                if osc_server:
                    stats = osc_server.get_statistics()
                    print(
                        f"OSC Stats: Received={stats['rx_count']}, Sent={stats['tx_count']}, Errors={stats['error_count']}")
                    print(f"Active Clients: {stats['active_clients']}")
            elif command == "clients":
                # Display all connected clients
                if osc_server:
                    with osc_server.clients_lock:
                        if not osc_server.clients:
                            print("No clients connected")
                        else:
                            print("\n=== Connected Clients ===")
                            for key, client in osc_server.clients.items():
                                addr = client["address"]
                                last_seen = time.time() - client["last_seen"]
                                subscribes = client.get("subscribe", [])
                                format_type = client.get("format", "unknown")

                                print(f"Client: {addr[0]}:{addr[1]}")
                                print(
                                    f"  Last active: {last_seen:.1f} seconds ago")
                                print(
                                    f"  Subscriptions: {', '.join(subscribes) if subscribes else 'none'}")
                                print(f"  Format: {format_type}")
                                print("")
            elif command == "send":
                # Send a test message
                data = simulator.get_data()
                data["type"] = "test_message"
                data["message"] = "This is a test message"

                # 1. Send via broadcast
                clients_count = osc_server.broadcast("/encoder/test", data)
                print(
                    f"Sent test message via broadcast to {clients_count} clients")

                # 2. Send direct message to localhost:9000
                test_client = udp_client.SimpleUDPClient("127.0.0.1", 9000)
                test_client.send_message(
                    "/encoder/direct_test", json.dumps(data))
                print("Sent direct test message to 127.0.0.1:9000")
            elif command == "pos" and len(cmd_parts) > 1:
                try:
                    pos = float(cmd_parts[1])
                    simulator.set_position(pos)
                    print(f"Position set to {simulator.position:.2f}°")

                    # Broadcast position update immediately
                    data = simulator.get_data()
                    data["type"] = "position_update"
                    data["message"] = f"Position manually set to {simulator.position:.2f}°"

                    # Try both broadcasting and direct messaging
                    osc_server.broadcast("/encoder/position_update", data)

                    # Also send direct message for testing
                    test_client = udp_client.SimpleUDPClient("127.0.0.1", 9000)
                    test_client.send_message(
                        "/encoder/position_update", json.dumps(data))

                except ValueError:
                    print("Invalid position value")
            elif command == "speed" and len(cmd_parts) > 1:
                try:
                    speed = float(cmd_parts[1])
                    simulator.set_speed(speed)
                    print(f"Speed set to {simulator.speed:.2f} RPM")
                except ValueError:
                    print("Invalid speed value")
            elif command == "dir" and len(cmd_parts) > 1:
                try:
                    direction = int(cmd_parts[1])
                    if direction not in [1, -1]:
                        print("Direction value must be 1 (CW) or -1 (CCW)")
                    else:
                        simulator.set_direction(direction)
                        direction_text = "Clockwise (CW)" if direction > 0 else "Counter-clockwise (CCW)"
                        print(f"Direction set to {direction_text}")
                except ValueError:
                    print("Invalid direction value")
            elif command == "toggle":
                status = simulator.toggle_rotation()
                status_text = "ON" if status else "OFF"
                print(f"Auto-rotation {status_text}")
            elif command == "zero":
                simulator.position = 0.0
                simulator.laps = 0
                simulator.multi_position = 0.0
                print("Zero point set")

                # Use OSC server to broadcast zero point setting message
                if osc_server:
                    zero_msg = {
                        "status": "success",
                        "type": "zero_set",
                        "message": "Zero point set successfully",
                        "position": 0.0,
                        "multi_position": 0.0,
                        "laps": 0
                    }
                    # Broadcast to all clients
                    clients_count = osc_server.broadcast(
                        "/encoder/zero_set", zero_msg)
                    print(
                        f"Zero point notification sent to {clients_count} clients")

                    # Also send direct message
                    test_client = udp_client.SimpleUDPClient("127.0.0.1", 9000)
                    test_client.send_message(
                        "/encoder/zero_set", json.dumps(zero_msg))
                    print("Sent direct zero point message to 127.0.0.1:9000")
            elif command == "gpio" and len(cmd_parts) > 2:
                try:
                    pin = int(cmd_parts[1])
                    state = int(cmd_parts[2])
                    if 0 <= pin < len(simulator.gpio_states) and state in [0, 1]:
                        simulator.gpio_states[pin] = bool(state)
                        print(f"GPIO {pin} set to {state}")

                        # Use OSC server to broadcast GPIO state change
                        if osc_server:
                            gpio_msg = {
                                "status": "success",
                                "pin": pin,
                                "state": bool(state)
                            }
                            osc_server.broadcast("/gpio/state", gpio_msg)
                    else:
                        print("Invalid PIN or state")
                except ValueError:
                    print("Invalid parameters")
            elif command == "interval" and len(cmd_parts) > 1:
                try:
                    new_interval = float(cmd_parts[1])
                    if new_interval > 0:
                        current_interval = new_interval
                        print(
                            f"Data sending interval set to {current_interval:.2f} seconds")
                    else:
                        print("Interval must be greater than 0")
                except ValueError:
                    print("Invalid interval value")
            else:
                print(
                    f"Unknown command: {command}, enter 'help' for assistance")

        except KeyboardInterrupt:
            running = False
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")


def main():
    """Main function"""
    global running, osc_server, quiet_mode

    # Initialize global quiet mode flag
    quiet_mode = False

    # Command line argument parsing
    parser = argparse.ArgumentParser(
        description="Encoder OSC Communication Simulator")
    parser.add_argument("-i", "--interactive",
                        action="store_true", help="Start interactive mode")
    parser.add_argument("-d", "--debug", action="store_true",
                        help="Enable debug mode")
    parser.add_argument("--listen-host", type=str,
                        default="0.0.0.0", help="Listening host address")
    parser.add_argument("--listen-port", type=int,
                        default=9001, help="Listening port")
    parser.add_argument("--return-port", type=int,
                        default=9000, help="Return message port")
    parser.add_argument("--interval", type=float,
                        default=0.5, help="Data sending interval in seconds")
    parser.add_argument("--auto-rotate", action="store_true",
                        help="Auto-rotate at startup")
    parser.add_argument("--speed", type=float, default=10.0,
                        help="Initial speed in RPM")

    args = parser.parse_args()

    # Configure logging
    setup_logging(args.debug)

    try:
        # Create simulator
        simulator = EncoderSimulator()
        simulator.set_speed(args.speed)
        simulator.auto_rotate = args.auto_rotate
        simulator.interactive_mode = False  # Add this attribute

        # Start enhanced OSC server
        osc_server, _ = start_osc_server(
            args.listen_host, args.listen_port, args.return_port, simulator)

        if not osc_server:
            print("Could not start OSC server, exiting...")
            return 1

        # Direct test message - only send in non-interactive mode
        if not args.interactive:
            try:
                test_client = udp_client.SimpleUDPClient(
                    "127.0.0.1", args.return_port)
                test_client.send_message("/test/startup", json.dumps({
                    "message": "Simulator started",
                    "timestamp": time.time()
                }))
                print(
                    f"Sent startup test message to 127.0.0.1:{args.return_port}")
            except Exception as e:
                print(f"Error sending startup message: {e}")

        # Make osc_server accessible globally for client registration
        globals()['osc_server'] = osc_server

        # Add this immediately after creating osc_server
        # Patch the broadcast method of osc_server to respect quiet_mode
        if osc_server:
            original_broadcast = osc_server.broadcast

            def quiet_broadcast(address, data):
                global quiet_mode
                # Only print if not in quiet mode
                if not quiet_mode:
                    print(f"Broadcasting to 1 clients: {address}")
                # Call the original method
                return original_broadcast(address, data)

            # Replace the method with our wrapped version
            osc_server.broadcast = quiet_broadcast

        # Start data sending thread
        sender_thread = Thread(target=send_periodic_updates,
                               args=(osc_server, simulator, args.interval))
        sender_thread.daemon = True
        sender_thread.start()

        # Register a client for localhost automatically
        with osc_server.clients_lock:
            client_key = f"127.0.0.1:{args.return_port}"
            if client_key not in osc_server.clients:
                osc_server.clients[client_key] = {
                    "address": ("127.0.0.1", args.return_port),
                    "last_seen": time.time(),
                    "subscribe": ["monitor"],
                    "format": "json"
                }
                print(f"Auto-registered localhost client to receive data")

        if args.interactive:
            # Enable quiet mode for interactive sessions
            quiet_mode = True
            if hasattr(osc_server, 'quiet_mode'):
                osc_server.quiet_mode = True

            # Interactive mode
            interactive_mode(simulator, osc_server, args.interval)
        else:
            # Service mode
            print("Simulator started, press Ctrl+C to stop...")

            # Main loop
            while running:
                # Send a direct message every 5 seconds to verify OSC functionality
                test_client.send_message(
                    "/test/heartbeat", f"Heartbeat {time.time()}")
                time.sleep(1)

    except Exception as e:
        logging.exception(f"Simulator runtime error: {e}")
        return 1
    finally:
        # Stop all threads
        stop_event.set()

        # Stop OSC server
        if 'osc_server' in locals() and osc_server:
            osc_server.stop()

        print("Simulator closed")

    return 0


if __name__ == "__main__":
    sys.exit(main())
