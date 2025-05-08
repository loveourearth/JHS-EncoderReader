import sys
import time
import logging
import os
import threading
from datetime import datetime
from pythonosc.udp_client import SimpleUDPClient
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

# Optional: Color output
try:
    from colorama import init, Fore, Style
    init()
except ImportError:
    class Fore:
        GREEN = YELLOW = RED = RESET = ''
    class Style:
        RESET_ALL = ''

SERVER_IP = "192.168.68.68"
SERVER_PORT = 8888
CLIENT_LISTEN_IP = "0.0.0.0"
CLIENT_LISTEN_PORT = 9999

client = SimpleUDPClient(SERVER_IP, SERVER_PORT)

def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    color = {
        "INFO": Fore.GREEN,
        "SEND": Fore.YELLOW,
        "RECV": Fore,CYAN,
        "ERROR": Fore.RED
    }.get(level, "")
    print(f"{color}[{level} {timestamp}] {message}{Style.RESET_ALL}")


def handle_response(address, *args):
    if "/encoder/data" in address and len(args) >= 3:
        laps, angle, rpm = args[:3]
        print(f"device:{address:<25} | laps: {laps:<3} | angle: {angle:<6} | rpm: {rpm:<6}", "RECV")

def start_listener():
    dispatcher = Dispatcher()
    for path in [
        "/encoder/data",
        "/encoder/monitor/start",
        "/encoder/monitor/stop",
        "/encoder/set_zero",
        "/encoder/error",
        "/gpio/response",
        "/gpio/input",
        "text",
        "/response",
        "/system/heartbeat",
        "/device_info"
    ]:
        dispatcher.map(path, handle_response)
    dispatcher.set_default_handler(handle_response)

    server = ThreadingOSCUDPServer((CLIENT_LISTEN_IP, CLIENT_LISTEN_PORT), dispatcher)
    log(f"OSC Listening on {CLIENT_LISTEN_IP}:{CLIENT_LISTEN_PORT}", "INFO")
    server.serve_forever()

# API Sender
if __name__ == "__main__":
    threading.Thread(target=start_listener, daemon=True).start()

    client.send_message("/encoder/set_zero", [])
    log("/encoder/set_zero", "SEND")
    time.sleep(1)

    client.send_message("/encoder/start_monitor", [0.1, "osc"])
    log("/start_monitor", "SEND")
    time.sleep(1)


    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("Keyboard interrupt received. Stopping...", "ERROR")

    # Send stop_monitor
    client.send_message("/encoder/stop_monitor", [])
    log("/encoder/stop_monitor", "SEND")
    log("Client shut down.", "INFO")

