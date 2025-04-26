# Modbus Encoder Control System (English Version)

A Python-based encoder control system using Modbus-RTU communication protocol to connect to encoder devices, providing GPIO control and OSC network interface. The system is designed with asynchronous mode, supporting connection monitoring, automatic reconnection, and heartbeat mechanisms.

## Features

- **Encoder Control**: Read position, speed, set zero point, monitor rotation direction and lap count
- **GPIO Control**: Control output pins, read input pins, generate pulse signals
- **OSC Network Interface**: UDP/OSC protocol supporting multiple client connections
- **Asynchronous Execution**: Efficient I/O operations and resource management
- **Robust Connection**: Heartbeat mechanism and automatic reconnection ensure stable long-term operation
- **Smart Monitoring**: Each client establishes only one monitoring task, avoiding resource waste

## Device Naming Mechanism

The system now uses the hostname as the device identification name, eliminating the need for configuration in `settings.json`.

- **Automatic Hostname Usage**: The system automatically obtains your system hostname (e.g., `rpi301`) and uses it as the device identification name
- **No Manual Configuration Required**: You don't need to modify any configuration files as the system automatically detects and uses the hostname
- **Consistency Maintained**: Even when executing `git pull` to update the code, your device identification settings remain unaffected

This mechanism is particularly suitable for multi-device environments, allowing each device to automatically use its hostname for identification, making management and monitoring more intuitive.

## Rotation Direction States

The system uses three states to indicate the encoder's rotation direction:

- **1**: Forward rotation (clockwise), shown as `direction` value of 1 in OSC messages
- **0**: Stopped state, speed below threshold (approx. 1 RPM)
- **-1**: Reverse rotation (counterclockwise)

This three-state system is more precise than the previous binary system, allowing you to better determine the encoder's current motion status.

## Installation

```bash
# Clone the project and enter directory
git clone https://github.com/loveourearth/JHS-EncoderReader.git
cd JHS-EncoderReader

# Install dependencies using Poetry
poetry install

# Start the system (asynchronous mode)
poetry run python main.py --async-mode
```

## Update and Restart Instructions

After updating the code with `git pull`, you need to restart the application for changes to take effect:

```bash
# Update code
git pull
```

**If you are using systemd to manage the service**:
```bash
# Restart the systemd service
sudo systemctl restart encoder-reader.service
```

**If you are running the program in other ways**:
- If running directly in a terminal, press Ctrl+C to stop the current process and then restart it
- If using other process managers (like supervisor or PM2), use their respective restart commands

## System Configuration

Configure system parameters through the `settings.json` file (note: device section is no longer needed):

```json
{
    "serial": {
        "port": "/dev/ttyUSB0",
        "baudrate": 9600
    },
    "osc": {
        "host": "0.0.0.0",
        "port": 8888,
        "return_port": 9999,
        "heartbeat_interval": 120,
        "heartbeat_enabled": true
    }
}
```

## OSC Communication Port Description

The system uses two different ports for OSC communication:

- **Port 8888**: The server listens on this port to receive commands from clients
- **Port 9999**: The server sends responses and data to clients through this port

**Important**: Clients must be configured to send commands to port 8888 and listen for responses on port 9999.
In some OSC client libraries, this requires setting different input and output ports.

## Heartbeat Mechanism

The system uses a bidirectional heartbeat mechanism to ensure connection stability:

1. **Server Heartbeat**: The system sends heartbeat messages to all clients at the `/system/heartbeat` address every `heartbeat_interval` seconds (default 120 seconds)
2. **Client Heartbeat**: Clients should periodically send `/whoami` requests to maintain active connections, recommended every 60-90 seconds

**Important Note**: Client connections inactive for extended periods (over 5 minutes) will be automatically cleaned up by the system. For long-running applications, clients must implement a mechanism to send `/whoami` to maintain the connection.

## OSC Commands

The system provides the following main commands via UDP/OSC protocol:

### System Commands

- **/whoami** - Get device identity information (also serves as heartbeat to maintain connection)
  ```
  /whoami
  ```

### Encoder Operations

- **/encoder/set_zero** - Set encoder zero point
  ```
  /encoder/set_zero
  ```

- **/encoder/start_monitor [interval]** - Start monitoring encoder data (using OSC format by default)
  ```
  /encoder/start_monitor 0.5  # Monitor every 0.5 seconds
  ```
  
- **/encoder/stop_monitor** - Stop all encoder data monitoring
  ```
  /encoder/stop_monitor
  ```

### GPIO Operations

- **/gpio high [pin]** - Set GPIO output to high level
  ```
  /gpio high 0      # Set pin index 0 to high level
  /gpio high gpio 17  # Set GPIO 17 to high level
  ```

- **/gpio low [pin]** - Set GPIO output to low level
  ```
  /gpio low 0       # Set pin index 0 to low level
  ```

- **/gpio toggle [pin]** - Toggle GPIO output state
  ```
  /gpio toggle 0    # Toggle state of pin index 0
  ```

- **/gpio pulse [pin] [duration]** - Generate GPIO pulse
  ```
  /gpio pulse 0 0.5   # Generate 0.5 second pulse
  ```

- **/gpio read** - Read GPIO input state
  ```
  /gpio read        # Read input pin state
  ```

## OSC Response Format

The system uses OSC format as the default response format, particularly suitable for real-time control scenarios:

Monitoring data is sent to address: `/[device-name]/encoder/data`
Parameter list: [address, timestamp, direction, angle, rpm, laps, raw_angle, raw_rpm]

For example:  
Address: `/rpi301/encoder/data`  
Parameters: `[1, 1635423016.789, 0, 180.0, 60.0, 0, 2048, 1024]`

If using text format, data is sent space-separated to the `/[device-name]/text` address:
```
1 1635423016.789 0 180.0000 60.0000 0 2048 1024
```

## Smart Monitoring Features

The system implements the following smart monitoring mechanisms to ensure efficient and stable operation in multi-client environments:

1. **Singleton Mode Monitoring**: Each client address can only have one active monitoring task; new monitoring requests will stop old tasks
2. **Duplicate Data Filtering**: Intelligently detects and filters identical data sent within short time periods, reducing network traffic and system load
3. **Automatic Resource Management**: When clients disconnect, related monitoring tasks are automatically cleaned up, freeing system resources

These mechanisms collectively ensure the system remains efficient and stable during long-term operation.

## Command Line Options

- `-d, --debug`: Enable debug mode
- `-p PORT, --port PORT`: Specify serial port device
- `-b BAUDRATE, --baudrate BAUDRATE`: Specify baud rate
- `-a ADDRESS, --address ADDRESS`: Specify slave address
- `--async-mode`: Run in asynchronous mode (recommended as default)
- `-c, --command`: Execute a single command and exit