"""
Peristaltic Pump Controller Module

Provides high-level control for Innofluid OEM-AMCB209 peristaltic pumps via Modbus RTU.
Supports RS485 communication with multiple pumps on a single bus.
"""

import logging
import struct
import threading
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import List, Optional, Callable

import serial
from serial import SerialException

logger = logging.getLogger(__name__)


# =============================================================================
# CRC-16 Modbus
# =============================================================================

CRC16_TABLE = [
    0x0000, 0xC0C1, 0xC181, 0x0140, 0xC301, 0x03C0, 0x0280, 0xC241,
    0xC601, 0x06C0, 0x0780, 0xC741, 0x0500, 0xC5C1, 0xC481, 0x0440,
    0xCC01, 0x0CC0, 0x0D80, 0xCD41, 0x0F00, 0xCFC1, 0xCE81, 0x0E40,
    0x0A00, 0xCAC1, 0xCB81, 0x0B40, 0xC901, 0x09C0, 0x0880, 0xC841,
    0xD801, 0x18C0, 0x1980, 0xD941, 0x1B00, 0xDBC1, 0xDA81, 0x1A40,
    0x1E00, 0xDEC1, 0xDF81, 0x1F40, 0xDD01, 0x1DC0, 0x1C80, 0xDC41,
    0x1400, 0xD4C1, 0xD581, 0x1540, 0xD701, 0x17C0, 0x1680, 0xD641,
    0xD201, 0x12C0, 0x1380, 0xD341, 0x1100, 0xD1C1, 0xD081, 0x1040,
    0xF001, 0x30C0, 0x3180, 0xF141, 0x3300, 0xF3C1, 0xF281, 0x3240,
    0x3600, 0xF6C1, 0xF781, 0x3740, 0xF501, 0x35C0, 0x3480, 0xF441,
    0x3C00, 0xFCC1, 0xFD81, 0x3D40, 0xFF01, 0x3FC0, 0x3E80, 0xFE41,
    0xFA01, 0x3AC0, 0x3B80, 0xFB41, 0x3900, 0xF9C1, 0xF881, 0x3840,
    0x2800, 0xE8C1, 0xE981, 0x2940, 0xEB01, 0x2BC0, 0x2A80, 0xEA41,
    0xEE01, 0x2EC0, 0x2F80, 0xEF41, 0x2D00, 0xEDC1, 0xEC81, 0x2C40,
    0xE401, 0x24C0, 0x2580, 0xE541, 0x2700, 0xE7C1, 0xE681, 0x2640,
    0x2200, 0xE2C1, 0xE381, 0x2340, 0xE101, 0x21C0, 0x2080, 0xE041,
    0xA001, 0x60C0, 0x6180, 0xA141, 0x6300, 0xA3C1, 0xA281, 0x6240,
    0x6600, 0xA6C1, 0xA781, 0x6740, 0xA501, 0x65C0, 0x6480, 0xA441,
    0x6C00, 0xACC1, 0xAD81, 0x6D40, 0xAF01, 0x6FC0, 0x6E80, 0xAE41,
    0xAA01, 0x6AC0, 0x6B80, 0xAB41, 0x6900, 0xA9C1, 0xA881, 0x6840,
    0x7800, 0xB8C1, 0xB981, 0x7940, 0xBB01, 0x7BC0, 0x7A80, 0xBA41,
    0xBE01, 0x7EC0, 0x7F80, 0xBF41, 0x7D00, 0xBDC1, 0xBC81, 0x7C40,
    0xB401, 0x74C0, 0x7580, 0xB541, 0x7700, 0xB7C1, 0xB681, 0x7640,
    0x7200, 0xB2C1, 0xB381, 0x7340, 0xB101, 0x71C0, 0x7080, 0xB041,
    0x5000, 0x90C1, 0x9181, 0x5140, 0x9301, 0x53C0, 0x5280, 0x9241,
    0x9601, 0x56C0, 0x5780, 0x9741, 0x5500, 0x95C1, 0x9481, 0x5440,
    0x9C01, 0x5CC0, 0x5D80, 0x9D41, 0x5F00, 0x9FC1, 0x9E81, 0x5E40,
    0x5A00, 0x9AC1, 0x9B81, 0x5B40, 0x9901, 0x59C0, 0x5880, 0x9841,
    0x8801, 0x48C0, 0x4980, 0x8941, 0x4B00, 0x8BC1, 0x8A81, 0x4A40,
    0x4E00, 0x8EC1, 0x8F81, 0x4F40, 0x8D01, 0x4DC0, 0x4C80, 0x8C41,
    0x4400, 0x84C1, 0x8581, 0x4540, 0x8701, 0x47C0, 0x4680, 0x8641,
    0x8201, 0x42C0, 0x4380, 0x8341, 0x4100, 0x81C1, 0x8081, 0x4040,
]


def _calculate_crc(data: bytes) -> int:
    """Calculate Modbus CRC-16 checksum."""
    crc = 0xFFFF
    for byte in data:
        crc = (crc >> 8) ^ CRC16_TABLE[(crc ^ byte) & 0xFF]
    return crc


def _verify_crc(data: bytes) -> bool:
    """Verify CRC of a complete Modbus frame."""
    if len(data) < 3:
        return False
    received_crc = data[-2] | (data[-1] << 8)
    return _calculate_crc(data[:-2]) == received_crc


# =============================================================================
# Exceptions
# =============================================================================

class PumpError(Exception):
    """Base exception for pump errors."""
    pass


class CommunicationError(PumpError):
    """Communication error with the pump."""
    pass


class PumpAlarmError(PumpError):
    """Pump alarm condition."""
    pass


# =============================================================================
# Enumerations
# =============================================================================

class Direction(IntEnum):
    """Pump rotation direction."""
    CLOCKWISE = 1
    COUNTER_CLOCKWISE = -1


class PumpStatusBits(IntEnum):
    """Pump status register bits."""
    IN_PLACE = 0x01
    HOMING_COMPLETE = 0x02
    RUNNING = 0x04
    ALARM = 0x08
    RELEASED = 0x10


# =============================================================================
# Register Definitions
# =============================================================================

class _Reg:
    """Modbus register addresses for OEM-AMCB209 pump."""
    JOG_SPEED = 0x001D          # Jog speed (0.1 RPM units, signed)
    JOG_ACCEL = 0x001E          # Acceleration time (ms)
    JOG_DECEL = 0x001F          # Deceleration time (ms)
    MOTION_CMD = 0x0027         # Motion control command
    AUX_CMD = 0x002D            # Auxiliary command
    STATUS = 0x0007             # Status register
    CURRENT_SPEED = 0x000C      # Current speed (0.1 RPM units)


class _MotionCmd:
    """Motion command bits."""
    POSITION_START = 0x0001     # Position mode start
    SPEED_START = 0x0002        # Speed mode start
    STOP = 0x0100               # Normal stop (with decel)
    EMERGENCY_STOP = 0x0200     # Emergency stop (immediate)


class _AuxCmd:
    """Auxiliary command values."""
    RELEASE = 0x0011            # Release motor (disable)
    ENABLE = 0x0012             # Enable motor
    CLEAR_ALARM = 0x0021        # Clear alarm
    CLEAR_POSITION = 0x0031     # Clear position counter


# =============================================================================
# Pump Configuration
# =============================================================================

@dataclass
class PumpConfig:
    """Configuration parameters for a peristaltic pump."""

    max_speed_rpm: float = 150.0
    """Maximum speed in RPM."""

    min_speed_rpm: float = 0.1
    """Minimum speed in RPM."""

    default_speed_rpm: float = 60.0
    """Default speed in RPM."""

    default_accel_ms: int = 100
    """Default acceleration time in milliseconds."""

    default_decel_ms: int = 100
    """Default deceleration time in milliseconds."""

    ml_per_revolution: float = 0.0
    """Flow rate calibration: mL per revolution (0 = uncalibrated)."""

    def rpm_to_flow_rate(self, rpm: float) -> float:
        """
        Convert RPM to flow rate in mL/min.

        Returns 0 if not calibrated.
        """
        if self.ml_per_revolution <= 0:
            return 0.0
        return abs(rpm) * self.ml_per_revolution

    def flow_rate_to_rpm(self, ml_per_min: float) -> float:
        """
        Convert flow rate (mL/min) to RPM.

        Raises ValueError if not calibrated.
        """
        if self.ml_per_revolution <= 0:
            raise ValueError("Pump not calibrated (ml_per_revolution not set)")
        return ml_per_min / self.ml_per_revolution


# =============================================================================
# Modbus Client
# =============================================================================

class _ModbusClient:
    """Simple Modbus RTU client for pump communication."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 0.5,
        shared_serial: Optional[serial.Serial] = None,
    ):
        self._port_name = port
        self._baudrate = baudrate
        self._timeout = timeout
        self._serial = shared_serial
        self._owns_serial = shared_serial is None
        self._lock = threading.RLock()

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def connect(self) -> None:
        """Open serial connection."""
        if self._serial is not None and self._serial.is_open:
            return

        if self._owns_serial:
            self._serial = serial.Serial(
                port=self._port_name,
                baudrate=self._baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self._timeout,
            )
            logger.info(f"Connected to {self._port_name} @ {self._baudrate}")

    def disconnect(self) -> None:
        """Close serial connection if we own it."""
        if self._owns_serial and self._serial is not None:
            self._serial.close()
            self._serial = None
            logger.info("Disconnected")

    def read_register(self, slave_id: int, address: int) -> int:
        """Read a single 16-bit register (FC=0x03)."""
        frame = struct.pack('>BBHH', slave_id, 0x03, address, 1)
        crc = _calculate_crc(frame)
        request = frame + struct.pack('<H', crc)

        response = self._send_receive(request, 7)
        self._check_response(response, slave_id, 0x03)

        return struct.unpack('>H', response[3:5])[0]

    def write_register(self, slave_id: int, address: int, value: int) -> None:
        """Write a single 16-bit register (FC=0x06)."""
        frame = struct.pack('>BBHH', slave_id, 0x06, address, value & 0xFFFF)
        crc = _calculate_crc(frame)
        request = frame + struct.pack('<H', crc)

        response = self._send_receive(request, 8)
        self._check_response(response, slave_id, 0x06)

    def write_registers(self, slave_id: int, address: int, values: List[int]) -> None:
        """Write multiple 16-bit registers (FC=0x10)."""
        count = len(values)
        byte_count = count * 2
        frame = struct.pack('>BBHHB', slave_id, 0x10, address, count, byte_count)
        for val in values:
            frame += struct.pack('>H', val & 0xFFFF)
        crc = _calculate_crc(frame)
        request = frame + struct.pack('<H', crc)

        response = self._send_receive(request, 8)
        self._check_response(response, slave_id, 0x10)

    def _send_receive(self, request: bytes, expected_len: int) -> bytes:
        """Send request and receive response."""
        with self._lock:
            if not self.is_connected:
                raise CommunicationError("Not connected")

            self._serial.reset_input_buffer()
            self._serial.write(request)
            self._serial.flush()

            time.sleep(0.05)  # Wait for device to process

            response = b''
            retries = 10
            while len(response) < expected_len and retries > 0:
                chunk = self._serial.read(expected_len - len(response))
                if chunk:
                    response += chunk
                else:
                    retries -= 1
                    time.sleep(0.01)

            if len(response) < expected_len:
                raise CommunicationError(
                    f"Incomplete response: got {len(response)} bytes, expected {expected_len}"
                )

            return response

    def _check_response(self, response: bytes, expected_slave: int, expected_fc: int) -> None:
        """Validate response frame."""
        if not _verify_crc(response):
            raise CommunicationError("CRC error in response")

        if response[0] != expected_slave:
            raise CommunicationError(
                f"Slave address mismatch: expected {expected_slave}, got {response[0]}"
            )

        if response[1] & 0x80:
            error_code = response[2] if len(response) > 2 else 0
            raise CommunicationError(f"Modbus exception: code 0x{error_code:02X}")


# =============================================================================
# Peristaltic Pump Controller
# =============================================================================

class PeristalticPump:
    """
    High-level controller for Innofluid OEM-AMCB209 peristaltic pump.

    Provides simple methods for speed control, direction, and timed dispensing.

    Example usage:
        pump = PeristalticPump(port="/dev/ttyUSB0", address=1)
        pump.connect()
        pump.set_speed(60.0)  # 60 RPM
        pump.start()
        time.sleep(5)
        pump.stop()
        pump.disconnect()

    With context manager:
        with PeristalticPump(port="/dev/ttyUSB0") as pump:
            pump.run_for_time(10.0, speed_rpm=30.0)  # Run 10 seconds at 30 RPM
    """

    def __init__(
        self,
        port: str,
        address: int = 1,
        baudrate: int = 115200,
        config: Optional[PumpConfig] = None,
        shared_client: Optional[_ModbusClient] = None,
    ):
        """
        Initialize peristaltic pump controller.

        Args:
            port: Serial port name (e.g., "/dev/ttyUSB0" or "COM3")
            address: Modbus slave address (1-255)
            baudrate: Communication baud rate
            config: Pump configuration (uses defaults if None)
            shared_client: Shared Modbus client for multi-pump setups
        """
        self._port = port
        self._address = address
        self._baudrate = baudrate
        self._config = config or PumpConfig()

        self._client = shared_client
        self._owns_client = shared_client is None
        self._lock = threading.Lock()

        # Internal state
        self._speed_rpm = 0.0
        self._direction = Direction.CLOCKWISE
        self._is_running = False
        self._is_enabled = True

    @property
    def address(self) -> int:
        """Get Modbus slave address."""
        return self._address

    @property
    def is_connected(self) -> bool:
        """Check if communication is established."""
        return self._client is not None and self._client.is_connected

    @property
    def config(self) -> PumpConfig:
        """Get pump configuration."""
        return self._config

    @property
    def speed_rpm(self) -> float:
        """Get current speed setting in RPM."""
        return self._speed_rpm

    @property
    def direction(self) -> Direction:
        """Get current direction setting."""
        return self._direction

    # =========================================================================
    # Connection Management
    # =========================================================================

    def connect(self) -> None:
        """
        Connect to the pump.

        Establishes serial communication.

        Raises:
            CommunicationError: If connection fails
        """
        if self._owns_client:
            self._client = _ModbusClient(
                port=self._port,
                baudrate=self._baudrate,
                timeout=0.5,
            )

        self._client.connect()

        # Verify communication by reading status
        try:
            self.get_status()
            logger.info(f"Connected to pump at address {self._address}")
        except Exception as e:
            if self._owns_client:
                self._client.disconnect()
                self._client = None
            raise CommunicationError(f"Failed to communicate with pump: {e}")

        # Set default acceleration
        self.set_acceleration(
            accel_ms=self._config.default_accel_ms,
            decel_ms=self._config.default_decel_ms,
        )

    def disconnect(self) -> None:
        """Disconnect from the pump."""
        if self._owns_client and self._client is not None:
            self._client.disconnect()
            self._client = None
        logger.info("Disconnected from pump")

    # =========================================================================
    # Speed and Direction Control
    # =========================================================================

    def set_speed(self, speed_rpm: float) -> None:
        """
        Set pump speed.

        Args:
            speed_rpm: Speed in RPM (positive or negative).
                      Sign determines direction:
                      - Positive: Clockwise
                      - Negative: Counter-clockwise

        Raises:
            ValueError: If speed exceeds limits
            CommunicationError: If communication fails
        """
        self._check_connected()

        abs_speed = abs(speed_rpm)
        if abs_speed > self._config.max_speed_rpm:
            raise ValueError(
                f"Speed {abs_speed} RPM exceeds maximum {self._config.max_speed_rpm} RPM"
            )

        # Determine direction from sign
        if speed_rpm >= 0:
            self._direction = Direction.CLOCKWISE
        else:
            self._direction = Direction.COUNTER_CLOCKWISE

        self._speed_rpm = abs_speed

        # Convert to 0.1 RPM units (signed 16-bit)
        raw_speed = int(speed_rpm * 10)
        if raw_speed < 0:
            raw_speed = raw_speed & 0xFFFF  # Convert to unsigned representation

        with self._lock:
            self._write_register(_Reg.JOG_SPEED, raw_speed)

        logger.debug(f"Speed set to {speed_rpm} RPM")

    def set_direction(self, direction: Direction) -> None:
        """
        Set pump direction.

        Args:
            direction: Direction.CLOCKWISE or Direction.COUNTER_CLOCKWISE
        """
        self._check_connected()

        self._direction = direction

        # Re-apply speed with new direction
        signed_speed = self._speed_rpm * direction
        raw_speed = int(signed_speed * 10)
        if raw_speed < 0:
            raw_speed = raw_speed & 0xFFFF

        with self._lock:
            self._write_register(_Reg.JOG_SPEED, raw_speed)

        logger.debug(f"Direction set to {direction.name}")

    def set_acceleration(self, accel_ms: int = 100, decel_ms: int = 100) -> None:
        """
        Set acceleration and deceleration times.

        Args:
            accel_ms: Acceleration time in milliseconds (0-2000)
            decel_ms: Deceleration time in milliseconds (0-2000)
        """
        self._check_connected()

        accel_ms = max(0, min(2000, accel_ms))
        decel_ms = max(0, min(2000, decel_ms))

        with self._lock:
            self._write_registers(_Reg.JOG_ACCEL, [accel_ms, decel_ms])

        logger.debug(f"Acceleration: {accel_ms}ms, Deceleration: {decel_ms}ms")

    def set_flow_rate(self, ml_per_min: float) -> None:
        """
        Set pump speed by flow rate (requires calibration).

        Args:
            ml_per_min: Flow rate in mL/min (positive or negative for direction)

        Raises:
            ValueError: If pump not calibrated or flow rate exceeds limits
        """
        rpm = self._config.flow_rate_to_rpm(abs(ml_per_min))
        if ml_per_min < 0:
            rpm = -rpm
        self.set_speed(rpm)

    # =========================================================================
    # Motion Control
    # =========================================================================

    def start(self) -> None:
        """
        Start the pump at the current speed setting.

        The pump will run continuously until stop() is called.
        """
        self._check_connected()

        with self._lock:
            self._write_register(_Reg.MOTION_CMD, _MotionCmd.SPEED_START)
            self._is_running = True

        logger.info(f"Pump started at {self._speed_rpm} RPM {self._direction.name}")

    def stop(self) -> None:
        """
        Stop the pump with deceleration.

        Uses the configured deceleration time.
        """
        self._check_connected()

        with self._lock:
            self._write_register(_Reg.MOTION_CMD, _MotionCmd.STOP)
            self._is_running = False

        logger.info("Pump stopped")

    def emergency_stop(self) -> None:
        """
        Emergency stop - immediate stop without deceleration.
        """
        self._check_connected()

        with self._lock:
            self._write_register(_Reg.MOTION_CMD, _MotionCmd.EMERGENCY_STOP)
            self._is_running = False

        logger.warning("Pump emergency stopped")

    def enable(self) -> None:
        """
        Enable the motor (lock shaft).

        Motor must be enabled for rotation.
        """
        self._check_connected()

        with self._lock:
            self._write_register(_Reg.AUX_CMD, _AuxCmd.ENABLE)
            self._is_enabled = True

        logger.debug("Motor enabled")

    def release(self) -> None:
        """
        Release/disable the motor (free shaft).

        Allows manual rotation of the pump head.
        """
        self._check_connected()

        with self._lock:
            self._write_register(_Reg.AUX_CMD, _AuxCmd.RELEASE)
            self._is_enabled = False

        logger.debug("Motor released")

    def clear_alarm(self) -> None:
        """Clear any active alarms."""
        self._check_connected()

        with self._lock:
            self._write_register(_Reg.AUX_CMD, _AuxCmd.CLEAR_ALARM)

        logger.info("Alarm cleared")

    # =========================================================================
    # Timed Operations
    # =========================================================================

    def run_for_time(
        self,
        duration_seconds: float,
        speed_rpm: Optional[float] = None,
        direction: Optional[Direction] = None,
        wait: bool = True,
    ) -> Optional[threading.Thread]:
        """
        Run the pump for a specified duration.

        Args:
            duration_seconds: How long to run in seconds
            speed_rpm: Speed in RPM (uses current if None)
            direction: Direction (uses current if None)
            wait: If True, block until complete. If False, return thread.

        Returns:
            Thread object if wait=False, None otherwise
        """
        self._check_connected()

        # Apply speed/direction if specified
        if speed_rpm is not None:
            if direction == Direction.COUNTER_CLOCKWISE:
                speed_rpm = -abs(speed_rpm)
            self.set_speed(speed_rpm)
        elif direction is not None:
            self.set_direction(direction)

        def _run():
            self.start()
            time.sleep(duration_seconds)
            self.stop()

        if wait:
            _run()
            return None
        else:
            thread = threading.Thread(target=_run, daemon=True)
            thread.start()
            return thread

    def dispense_volume(
        self,
        volume_ml: float,
        speed_rpm: Optional[float] = None,
        direction: Optional[Direction] = None,
        wait: bool = True,
    ) -> Optional[threading.Thread]:
        """
        Dispense a specific volume (requires calibration).

        Args:
            volume_ml: Volume to dispense in mL
            speed_rpm: Speed in RPM (uses default if None)
            direction: Direction (uses CLOCKWISE if None)
            wait: If True, block until complete

        Returns:
            Thread object if wait=False, None otherwise

        Raises:
            ValueError: If pump not calibrated
        """
        if self._config.ml_per_revolution <= 0:
            raise ValueError("Pump not calibrated (ml_per_revolution not set)")

        if speed_rpm is None:
            speed_rpm = self._config.default_speed_rpm

        # Calculate duration
        flow_rate = self._config.rpm_to_flow_rate(speed_rpm)  # mL/min
        duration_seconds = (volume_ml / flow_rate) * 60.0

        return self.run_for_time(
            duration_seconds=duration_seconds,
            speed_rpm=speed_rpm,
            direction=direction,
            wait=wait,
        )

    # =========================================================================
    # Status Reading
    # =========================================================================

    def get_status(self) -> int:
        """
        Read the status register.

        Returns:
            Raw status register value
        """
        self._check_connected()
        return self._read_register(_Reg.STATUS)

    def get_current_speed(self) -> float:
        """
        Read the current actual speed from the pump.

        Returns:
            Current speed in RPM
        """
        self._check_connected()
        raw = self._read_register(_Reg.CURRENT_SPEED)
        return raw / 10.0

    def is_running(self) -> bool:
        """
        Check if pump is currently running (from hardware).

        Returns:
            True if pump is running
        """
        status = self.get_status()
        return bool(status & PumpStatusBits.RUNNING)

    def has_alarm(self) -> bool:
        """
        Check if pump has an active alarm.

        Returns:
            True if alarm is active
        """
        status = self.get_status()
        return bool(status & PumpStatusBits.ALARM)

    def is_released(self) -> bool:
        """
        Check if motor is released (disabled).

        Returns:
            True if motor is released
        """
        status = self.get_status()
        return bool(status & PumpStatusBits.RELEASED)

    # =========================================================================
    # Internal Methods
    # =========================================================================

    def _check_connected(self) -> None:
        if not self.is_connected:
            raise CommunicationError("Not connected to pump")

    def _read_register(self, address: int) -> int:
        return self._client.read_register(self._address, address)

    def _write_register(self, address: int, value: int) -> None:
        self._client.write_register(self._address, address, value)

    def _write_registers(self, address: int, values: List[int]) -> None:
        self._client.write_registers(self._address, address, values)

    # =========================================================================
    # Context Manager Support
    # =========================================================================

    def __enter__(self) -> "PeristalticPump":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._is_running:
            try:
                self.stop()
            except Exception:
                pass
        self.disconnect()

    def __repr__(self) -> str:
        status = "connected" if self.is_connected else "disconnected"
        return f"PeristalticPump({self._port}, addr={self._address}, {status})"


# =============================================================================
# Multi-Pump Bus Manager
# =============================================================================

class PumpBus:
    """
    Manager for multiple pumps on a single RS485 bus.

    Use this when connecting multiple pumps to the same USB-RS485 converter.

    Example:
        with PumpBus(port="/dev/ttyUSB0") as bus:
            pump1 = bus.get_pump(1)
            pump2 = bus.get_pump(2)
            pump1.set_speed(30)
            pump2.set_speed(60)
            pump1.start()
            pump2.start()
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 0.5,
    ):
        """
        Initialize the RS485 bus.

        Args:
            port: Serial port name
            baudrate: Serial baud rate
            timeout: Read timeout in seconds
        """
        self._port = port
        self._baudrate = baudrate
        self._timeout = timeout
        self._client: Optional[_ModbusClient] = None
        self._pumps: dict[int, PeristalticPump] = {}

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    def connect(self) -> None:
        """Open the serial connection."""
        self._client = _ModbusClient(
            port=self._port,
            baudrate=self._baudrate,
            timeout=self._timeout,
        )
        self._client.connect()
        logger.info(f"Pump bus connected on {self._port}")

    def disconnect(self) -> None:
        """Close the serial connection."""
        # Stop all pumps first
        for pump in self._pumps.values():
            try:
                if pump._is_running:
                    pump.stop()
            except Exception:
                pass

        if self._client is not None:
            self._client.disconnect()
            self._client = None

        self._pumps.clear()
        logger.info("Pump bus disconnected")

    def get_pump(
        self,
        address: int,
        config: Optional[PumpConfig] = None,
    ) -> PeristalticPump:
        """
        Get a pump controller for the specified address.

        Args:
            address: Modbus slave address (1-255)
            config: Pump configuration (optional)

        Returns:
            PeristalticPump instance sharing this bus
        """
        if address not in self._pumps:
            pump = PeristalticPump(
                port=self._port,
                address=address,
                baudrate=self._baudrate,
                config=config,
                shared_client=self._client,
            )
            self._pumps[address] = pump

        return self._pumps[address]

    def stop_all(self) -> None:
        """Stop all pumps on the bus."""
        for pump in self._pumps.values():
            try:
                pump.stop()
            except Exception as e:
                logger.error(f"Failed to stop pump {pump.address}: {e}")

    def __enter__(self) -> "PumpBus":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()


# =============================================================================
# Simulation Class
# =============================================================================

class PeristalticPumpSimulation:
    """
    Simulated peristaltic pump for testing without hardware.

    Provides the same interface as PeristalticPump.
    """

    def __init__(
        self,
        port: str = "SIM",
        address: int = 1,
        baudrate: int = 115200,
        config: Optional[PumpConfig] = None,
        simulate_timing: bool = True,
    ):
        self._port = port
        self._address = address
        self._config = config or PumpConfig()
        self._simulate_timing = simulate_timing

        self._speed_rpm = 0.0
        self._direction = Direction.CLOCKWISE
        self._is_running = False
        self._is_enabled = True
        self._is_connected = False
        self._has_alarm = False

        self._current_speed = 0.0
        self._accel_ms = 100
        self._decel_ms = 100

    @property
    def address(self) -> int:
        return self._address

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def config(self) -> PumpConfig:
        return self._config

    @property
    def speed_rpm(self) -> float:
        return self._speed_rpm

    @property
    def direction(self) -> Direction:
        return self._direction

    def connect(self) -> None:
        self._is_connected = True
        print(f"[SIM Pump {self._address}] Connected")

    def disconnect(self) -> None:
        self._is_connected = False
        print(f"[SIM Pump {self._address}] Disconnected")

    def set_speed(self, speed_rpm: float) -> None:
        abs_speed = abs(speed_rpm)
        if abs_speed > self._config.max_speed_rpm:
            raise ValueError(f"Speed exceeds maximum {self._config.max_speed_rpm} RPM")

        self._speed_rpm = abs_speed
        self._direction = Direction.CLOCKWISE if speed_rpm >= 0 else Direction.COUNTER_CLOCKWISE
        print(f"[SIM Pump {self._address}] Speed set to {speed_rpm} RPM")

    def set_direction(self, direction: Direction) -> None:
        self._direction = direction
        print(f"[SIM Pump {self._address}] Direction: {direction.name}")

    def set_acceleration(self, accel_ms: int = 100, decel_ms: int = 100) -> None:
        self._accel_ms = accel_ms
        self._decel_ms = decel_ms
        print(f"[SIM Pump {self._address}] Accel: {accel_ms}ms, Decel: {decel_ms}ms")

    def set_flow_rate(self, ml_per_min: float) -> None:
        rpm = self._config.flow_rate_to_rpm(abs(ml_per_min))
        if ml_per_min < 0:
            rpm = -rpm
        self.set_speed(rpm)

    def start(self) -> None:
        self._is_running = True
        self._current_speed = self._speed_rpm * self._direction
        print(f"[SIM Pump {self._address}] Started")

    def stop(self) -> None:
        self._is_running = False
        if self._simulate_timing:
            time.sleep(self._decel_ms / 1000.0)
        self._current_speed = 0.0
        print(f"[SIM Pump {self._address}] Stopped")

    def emergency_stop(self) -> None:
        self._is_running = False
        self._current_speed = 0.0
        print(f"[SIM Pump {self._address}] Emergency stopped")

    def enable(self) -> None:
        self._is_enabled = True
        print(f"[SIM Pump {self._address}] Enabled")

    def release(self) -> None:
        self._is_enabled = False
        print(f"[SIM Pump {self._address}] Released")

    def clear_alarm(self) -> None:
        self._has_alarm = False
        print(f"[SIM Pump {self._address}] Alarm cleared")

    def run_for_time(
        self,
        duration_seconds: float,
        speed_rpm: Optional[float] = None,
        direction: Optional[Direction] = None,
        wait: bool = True,
    ) -> Optional[threading.Thread]:
        if speed_rpm is not None:
            if direction == Direction.COUNTER_CLOCKWISE:
                speed_rpm = -abs(speed_rpm)
            self.set_speed(speed_rpm)
        elif direction is not None:
            self.set_direction(direction)

        def _run():
            self.start()
            time.sleep(duration_seconds)
            self.stop()

        if wait:
            _run()
            return None
        else:
            thread = threading.Thread(target=_run, daemon=True)
            thread.start()
            return thread

    def dispense_volume(
        self,
        volume_ml: float,
        speed_rpm: Optional[float] = None,
        direction: Optional[Direction] = None,
        wait: bool = True,
    ) -> Optional[threading.Thread]:
        if self._config.ml_per_revolution <= 0:
            raise ValueError("Pump not calibrated")

        if speed_rpm is None:
            speed_rpm = self._config.default_speed_rpm

        flow_rate = self._config.rpm_to_flow_rate(speed_rpm)
        duration_seconds = (volume_ml / flow_rate) * 60.0

        return self.run_for_time(duration_seconds, speed_rpm, direction, wait)

    def get_status(self) -> int:
        status = 0
        if self._is_running:
            status |= PumpStatusBits.RUNNING
        if not self._is_enabled:
            status |= PumpStatusBits.RELEASED
        if self._has_alarm:
            status |= PumpStatusBits.ALARM
        return status

    def get_current_speed(self) -> float:
        return self._current_speed if self._is_running else 0.0

    def is_running(self) -> bool:
        return self._is_running

    def has_alarm(self) -> bool:
        return self._has_alarm

    def is_released(self) -> bool:
        return not self._is_enabled

    def __enter__(self) -> "PeristalticPumpSimulation":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._is_running:
            self.stop()
        self.disconnect()

    def __repr__(self) -> str:
        status = "connected" if self._is_connected else "disconnected"
        return f"PeristalticPumpSimulation(addr={self._address}, {status})"
