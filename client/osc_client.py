import sys
import time
import logging
import os
import threading
import time
from pythonosc.udp_client import SimpleUDPClient
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer


SERVER_IP = "192.168.68.68"
SERVER_PORT = 8888
CLIENT_LISTEN_IP = "0.0.0.0"
CLIENT_LISTEN_PORT = 9999
client = SimpleUDPClient(SERVER_IP, SERVER_PORT)


def handle_response(address, *args):
    #print(f"Received encoder data: device ID: {address}, raw data: {args}")
    if "/encoder/data" in address and len(args) >= 3:
        laps = args[0]
        angle = args[1]*360/4069
        rpm = args[2]/4096/(0.1/60)
        print(f"[EXTRACTED]device name:{address}, laps: {laps}, angle: {angle}, rpm: {rpm}")

def start_listener():
    dispatcher = Dispatcher()
    dispatcher.map("/encoder/data", handle_response)
    dispatcher.map("/encoder/monitor/start", handle_response)
    dispatcher.map("/encoder/monitor/stop", handle_response)
    dispatcher.map("/encoder/set_zero", handle_response)
    dispatcher.map("/encoder/error", handle_response)
    dispatcher.map("/gpio/response", handle_response)
    dispatcher.map("/gpio/input", handle_response)
    dispatcher.map("text", handle_response)
    dispatcher.map("/response", handle_response)
    dispatcher.map("/system/heartbeat", handle_response)
    dispatcher.map("/device_info", handle_response)
    dispatcher.set_default_handler(handle_response)

    server = ThreadingOSCUDPServer((CLIENT_LISTEN_IP, CLIENT_LISTEN_PORT), dispatcher)
    print(f"[LISTENING] OSC on {CLIENT_LISTEN_IP}:{CLIENT_LISTEN_PORT}")
    server.serve_forever()

# API Sender
if __name__ == "__main__":
    listener_thread = threading.Thread(target=start_listener, daemon=True)
    listener_thread.start()

  
    client.send_message("/encoder/set_zero", [])
    print("[SENT] /encoder/set_zero")
    time.sleep(1)

    client.send_message("/encoder/start_monitor", [0.1, "osc"])
    print("[SENT] /start_monitor")
    time.sleep(1)


    try:
        while True:
            time.sleep(1)
            #client.send_message("/encoder/whoami", [])
    except KeyboardInterrupt:
        print("[STOPPED] Keyboard interrupt received. Stopping...")

    # Send stop_monitor
    client.send_message("/encoder/stop_monitor", [])
    print("[SENT] /encoder/stop_monitor")
    print("[EXIT] Client shut down.")

