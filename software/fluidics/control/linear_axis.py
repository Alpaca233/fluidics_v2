"""
Linear Axis Controller Module

Provides high-level control for servo motor driven linear axes via Modbus RTU.
Based on CiA402 standard and NiMotion servo motor protocol.
"""

import logging
import struct
import threading
import time
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import List, Optional, Union

import serial
from serial import SerialException
from serial.tools import list_ports

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


def _append_crc(data: bytes) -> bytes:
    """Append CRC-16 to data (little-endian)."""
    crc = _calculate_crc(data)
    return data + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def _verify_crc(data: bytes) -> bool:
    """Verify CRC of a complete frame."""
    if len(data) < 3:
        return False
    payload = data[:-2]
    received_crc = data[-2] | (data[-1] << 8)
    return _calculate_crc(payload) == received_crc


# =============================================================================
# Exceptions
# =============================================================================

class LinearAxisError(Exception):
    """Base exception for linear axis errors."""
    pass


class CommunicationError(LinearAxisError):
    """Communication error with the motor driver."""
    pass


class MotionError(LinearAxisError):
    """Motion-related error (fault, timeout, etc.)."""
    pass


# =============================================================================
# Enumerations
# =============================================================================

class DriveState(Enum):
    """CiA402 drive state machine states."""
    NOT_READY_TO_SWITCH_ON = "Not ready to switch on"
    SWITCH_ON_DISABLED = "Switch on disabled"
    READY_TO_SWITCH_ON = "Ready to switch on"
    SWITCHED_ON = "Switched on"
    OPERATION_ENABLED = "Operation enabled"
    QUICK_STOP_ACTIVE = "Quick stop active"
    FAULT_REACTION_ACTIVE = "Fault reaction active"
    FAULT = "Fault"
    UNKNOWN = "Unknown"


class OperationMode(IntEnum):
    """CiA402 operation modes."""
    PROFILE_POSITION = 1
    VELOCITY = 2
    PROFILE_VELOCITY = 3
    PROFILE_TORQUE = 4
    HOMING = 6
    INTERPOLATED_POSITION = 7


class HomingMethod(IntEnum):
    """Supported homing methods."""
    NO_HOMING = 0
    POSITIVE_LIMIT_SWITCH = 1
    NEGATIVE_LIMIT_SWITCH = 17
    HOME_SWITCH_POSITIVE = 7
    HOME_SWITCH_NEGATIVE = 23
    CURRENT_POSITIVE = 33  # Stall detection positive direction
    CURRENT_NEGATIVE = 34  # Stall detection negative direction
    CURRENT_POSITION_AS_HOME = 35


# =============================================================================
# Register Definitions (NiMotion Modbus mapping)
# =============================================================================

class _Reg:
    """Modbus register addresses for NiMotion servo driver."""
    CONTROL_WORD = 0x0380
    STATUS_WORD = 0x0381
    MODES_OF_OPERATION = 0x03C2
    MODES_OF_OPERATION_DISPLAY = 0x03C3
    TARGET_POSITION = 0x03E7
    POSITION_ACTUAL = 0x03C8
    VELOCITY_ACTUAL = 0x03D5
    PROFILE_VELOCITY = 0x03F8
    PROFILE_ACCELERATION = 0x03FC
    PROFILE_DECELERATION = 0x03FE
    HOMING_METHOD = 0x0416
    HOMING_SPEED_HIGH = 0x0417
    HOMING_SPEED_LOW = 0x0419
    HOMING_ACCELERATION = 0x041B
    HOMING_TIMEOUT = 0x012E
    BLOCKING_TORQUE = 0x0170
    BLOCKING_TIME = 0x0172
    ENCODER_RESOLUTION_NUM = 0x0406
    ENCODER_RESOLUTION_DEN = 0x0408
    GEAR_RATIO_NUM = 0x040C
    GEAR_RATIO_DEN = 0x040E
    POLARITY = 0x03F3
    ERROR_CODE = 0x0382
    # DI configuration
    DI1_FUNCTION = 0x00D5
    DI1_LOGIC = 0x00D6
    DI2_FUNCTION = 0x00D7
    DI2_LOGIC = 0x00D8
    DI3_FUNCTION = 0x00D9
    DI3_LOGIC = 0x00DA
    # DO configuration
    DO1_FUNCTION = 0x00F8
    DO1_LOGIC = 0x00F9
    DO_CONTROL = 0x0374


class _ControlWord:
    """Control word bit definitions."""
    SWITCH_ON = 0x0001
    ENABLE_VOLTAGE = 0x0002
    QUICK_STOP = 0x0004
    ENABLE_OPERATION = 0x0008
    NEW_SET_POINT = 0x0010
    ABS_REL = 0x0040
    FAULT_RESET = 0x0080
    HALT = 0x0100
    # Command combinations
    CMD_SHUTDOWN = 0x0006
    CMD_SWITCH_ON = 0x0007
    CMD_ENABLE_OPERATION = 0x000F
    CMD_DISABLE_OPERATION = 0x0007
    CMD_QUICK_STOP = 0x0002


class _StatusWord:
    """Status word bit definitions."""
    READY_TO_SWITCH_ON = 0x0001
    SWITCHED_ON = 0x0002
    OPERATION_ENABLED = 0x0004
    FAULT = 0x0008
    VOLTAGE_ENABLED = 0x0010
    QUICK_STOP = 0x0020
    SWITCH_ON_DISABLED = 0x0040
    WARNING = 0x0080
    TARGET_REACHED = 0x0400
    STATE_MASK = 0x006F


def _decode_drive_state(status_word: int) -> DriveState:
    """Decode drive state from status word."""
    state_bits = status_word & _StatusWord.STATE_MASK

    if status_word & _StatusWord.FAULT:
        if (state_bits & 0x004F) == 0x000F:
            return DriveState.FAULT_REACTION_ACTIVE
        return DriveState.FAULT

    if (state_bits & 0x006F) == 0x0027:
        return DriveState.OPERATION_ENABLED
    if (state_bits & 0x006F) == 0x0007:
        return DriveState.QUICK_STOP_ACTIVE
    if (state_bits & 0x006F) == 0x0023:
        return DriveState.SWITCHED_ON
    if (state_bits & 0x006F) == 0x0021:
        return DriveState.READY_TO_SWITCH_ON
    if (state_bits & 0x004F) == 0x0040:
        return DriveState.SWITCH_ON_DISABLED
    if (state_bits & 0x004F) == 0x0000:
        return DriveState.NOT_READY_TO_SWITCH_ON

    return DriveState.UNKNOWN


# =============================================================================
# Modbus RTU Communication
# =============================================================================

class _ModbusClient:
    """Simple Modbus RTU client for servo motor communication."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 0.5,
        retries: int = 3,
    ):
        self._port_name = port
        self._baudrate = baudrate
        self._timeout = timeout
        self._retries = retries
        self._serial: Optional[serial.Serial] = None
        self._lock = threading.RLock()

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def connect(self) -> None:
        """Open serial connection."""
        with self._lock:
            if self._serial is not None and self._serial.is_open:
                return
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
        """Close serial connection."""
        with self._lock:
            if self._serial is not None:
                self._serial.close()
                self._serial = None
                logger.info("Disconnected")

    def read_register(self, slave_id: int, address: int) -> int:
        """Read a single 16-bit register (FC=0x03)."""
        values = self._read_holding_registers(slave_id, address, 1)
        return values[0]

    def read_register_32bit(self, slave_id: int, address: int, signed: bool = False) -> int:
        """Read two consecutive registers as 32-bit value (big-endian)."""
        values = self._read_holding_registers(slave_id, address, 2)
        value = (values[0] << 16) | values[1]
        if signed and value >= 0x80000000:
            value -= 0x100000000
        return value

    def write_register(self, slave_id: int, address: int, value: int) -> None:
        """Write a single 16-bit register (FC=0x06)."""
        self._write_single_register(slave_id, address, value)

    def write_register_32bit(self, slave_id: int, address: int, value: int, signed: bool = False) -> None:
        """Write two consecutive registers as 32-bit value (big-endian)."""
        if signed and value < 0:
            value += 0x100000000
        high = (value >> 16) & 0xFFFF
        low = value & 0xFFFF
        self._write_multiple_registers(slave_id, address, [high, low])

    def _read_holding_registers(self, slave_id: int, address: int, quantity: int) -> List[int]:
        """Read holding registers (FC=0x03)."""
        request = struct.pack(">BBHH", slave_id, 0x03, address, quantity)
        request = _append_crc(request)
        expected_len = 5 + quantity * 2

        response = self._send_receive(request, expected_len)
        if len(response) < expected_len:
            raise CommunicationError(f"Incomplete response: got {len(response)} bytes, expected {expected_len}")

        byte_count = response[2]
        registers = []
        for i in range(quantity):
            val = (response[3 + i * 2] << 8) | response[4 + i * 2]
            registers.append(val)
        return registers

    def _write_single_register(self, slave_id: int, address: int, value: int) -> None:
        """Write single register (FC=0x06)."""
        request = struct.pack(">BBHH", slave_id, 0x06, address, value & 0xFFFF)
        request = _append_crc(request)
        self._send_receive(request, 8)

    def _write_multiple_registers(self, slave_id: int, address: int, values: List[int]) -> None:
        """Write multiple registers (FC=0x10)."""
        quantity = len(values)
        byte_count = quantity * 2
        data = struct.pack(">BBHHB", slave_id, 0x10, address, quantity, byte_count)
        for v in values:
            data += struct.pack(">H", v & 0xFFFF)
        request = _append_crc(data)
        self._send_receive(request, 8)

    def _send_receive(self, request: bytes, expected_len: int) -> bytes:
        """Send request and receive response with retries."""
        with self._lock:
            if not self.is_connected:
                raise CommunicationError("Not connected")

            last_error = None
            for attempt in range(self._retries + 1):
                try:
                    self._serial.reset_input_buffer()
                    self._serial.write(request)
                    time.sleep(0.003)

                    response = b""
                    start = time.time()
                    while len(response) < expected_len and (time.time() - start) < self._timeout:
                        chunk = self._serial.read(expected_len - len(response))
                        if chunk:
                            response += chunk

                    if len(response) < 3:
                        raise CommunicationError("No response from device")

                    if not _verify_crc(response):
                        raise CommunicationError("CRC error in response")

                    # Check for exception response
                    if response[1] & 0x80:
                        exc_code = response[2] if len(response) > 2 else 0
                        raise CommunicationError(f"Modbus exception: FC=0x{response[1]:02X}, code=0x{exc_code:02X}")

                    return response

                except (SerialException, CommunicationError) as e:
                    last_error = e
                    if attempt < self._retries:
                        time.sleep(0.01)
                    continue

            raise CommunicationError(f"Communication failed after {self._retries + 1} attempts: {last_error}")


# =============================================================================
# Axis Configuration
# =============================================================================

@dataclass
class AxisConfig:
    """Configuration parameters for a linear axis."""

    # Mechanical parameters
    ball_screw_lead: float = 10.0
    """Ball screw lead in mm per revolution."""

    encoder_resolution: int = 10000
    """Encoder pulses per motor revolution."""

    stroke_min: float = 0.0
    """Minimum position in mm."""

    stroke_max: float = 100.0
    """Maximum position in mm."""

    # Motion parameters
    max_velocity: float = 100.0
    """Maximum velocity in mm/s."""

    default_velocity: float = 50.0
    """Default velocity in mm/s."""

    default_acceleration: float = 200.0
    """Default acceleration in mm/s^2."""

    # Homing parameters
    homing_method: HomingMethod = HomingMethod.NEGATIVE_LIMIT_SWITCH
    """Homing method to use."""

    homing_velocity_high: float = 20.0
    """High speed for homing (searching for switch) in mm/s."""

    homing_velocity_low: float = 5.0
    """Low speed for homing (searching for index) in mm/s."""

    homing_acceleration: float = 50.0
    """Acceleration during homing in mm/s^2."""

    homing_timeout: int = 60000
    """Homing timeout in milliseconds."""

    # Stall detection parameters (for stall homing)
    blocking_torque: int = 300
    """Torque threshold for stall detection (0.1% units, 300 = 30%)."""

    blocking_time: int = 500
    """Time to detect stall in milliseconds."""

    # Direction configuration
    velocity_polarity: int = 1
    """Velocity direction multiplier (1 or -1)."""

    driver_polarity: int = 0x00
    """Driver polarity register value (607Eh)."""

    # Digital I/O configuration
    di2_function: Optional[int] = 15  # Negative limit
    di2_logic: int = 0
    di3_function: Optional[int] = 14  # Positive limit
    di3_logic: int = 0

    # Brake configuration
    has_brake: bool = False
    """Whether axis has a holding brake."""

    brake_release_delay_ms: int = 500
    """Delay after enabling to allow brake release."""

    @property
    def pulses_per_mm(self) -> float:
        """Pulses per millimeter of travel."""
        return self.encoder_resolution / self.ball_screw_lead

    @property
    def mm_per_pulse(self) -> float:
        """Millimeters per encoder pulse."""
        return self.ball_screw_lead / self.encoder_resolution

    def mm_to_pulses(self, mm: float) -> int:
        """Convert millimeters to encoder pulses."""
        return int(mm * self.pulses_per_mm)

    def pulses_to_mm(self, pulses: int) -> float:
        """Convert encoder pulses to millimeters."""
        return pulses * self.mm_per_pulse

    def velocity_mm_to_pulses(self, velocity_mm_s: float) -> int:
        """Convert velocity from mm/s to pulses/s."""
        return int(velocity_mm_s * self.pulses_per_mm)

    def velocity_pulses_to_mm(self, velocity_pulses_s: int) -> float:
        """Convert velocity from pulses/s to mm/s."""
        return velocity_pulses_s * self.mm_per_pulse

    def is_position_valid(self, position_mm: float) -> bool:
        """Check if position is within stroke limits."""
        return self.stroke_min <= position_mm <= self.stroke_max


# =============================================================================
# Linear Axis Controller
# =============================================================================

class LinearAxis:
    """
    High-level controller for a servo motor driven linear axis.

    Provides simple methods for homing, positioning, and status monitoring.

    Example usage:
        axis = LinearAxis(port="/dev/ttyUSB0", slave_id=1)
        axis.connect()
        axis.enable()
        axis.home()
        axis.move_to(50.0)  # Move to 50mm
        print(f"Position: {axis.get_position()} mm")
        axis.disable()
        axis.disconnect()
    """

    DEFAULT_MOTION_TIMEOUT = 30.0
    DEFAULT_STATE_TIMEOUT = 2.0
    POLL_INTERVAL = 0.01

    def __init__(
        self,
        port: str,
        slave_id: int = 1,
        baudrate: int = 115200,
        config: Optional[AxisConfig] = None,
    ):
        """
        Initialize linear axis controller.

        Args:
            port: Serial port name (e.g., "/dev/ttyUSB0" or "COM3")
            slave_id: Modbus slave address (1-247)
            baudrate: Communication baud rate
            config: Axis configuration (uses defaults if None)
        """
        self._port = port
        self._slave_id = slave_id
        self._baudrate = baudrate
        self._config = config or AxisConfig()

        self._client: Optional[_ModbusClient] = None
        self._is_homed = False
        self._motion_timeout = self.DEFAULT_MOTION_TIMEOUT

    @property
    def is_connected(self) -> bool:
        """Check if communication is established."""
        return self._client is not None and self._client.is_connected

    @property
    def is_homed(self) -> bool:
        """Check if axis has been homed."""
        return self._is_homed

    @property
    def config(self) -> AxisConfig:
        """Get axis configuration."""
        return self._config

    # =========================================================================
    # Connection Management
    # =========================================================================

    def connect(self) -> None:
        """
        Connect to the motor driver.

        Establishes serial communication and initializes motor parameters.

        Raises:
            CommunicationError: If connection fails
        """
        self._client = _ModbusClient(
            port=self._port,
            baudrate=self._baudrate,
            timeout=0.5,
            retries=3,
        )
        self._client.connect()

        # Verify communication by reading status
        try:
            self._read_status_word()
            logger.info(f"Connected to axis at slave {self._slave_id}")
        except Exception as e:
            self._client.disconnect()
            self._client = None
            raise CommunicationError(f"Failed to communicate with motor: {e}")

        # Initialize motor parameters
        self._initialize_parameters()

    def disconnect(self) -> None:
        """Disconnect from the motor driver."""
        if self._client is not None:
            self._client.disconnect()
            self._client = None
        self._is_homed = False
        logger.info("Disconnected from axis")

    def _initialize_parameters(self) -> None:
        """Initialize motor parameters from configuration."""
        cfg = self._config

        # Set encoder resolution
        self._write_register_32bit(_Reg.ENCODER_RESOLUTION_NUM, cfg.encoder_resolution)
        self._write_register_32bit(_Reg.ENCODER_RESOLUTION_DEN, 1)

        # Set gear ratio (1:1 for direct drive)
        self._write_register_32bit(_Reg.GEAR_RATIO_NUM, 1)
        self._write_register_32bit(_Reg.GEAR_RATIO_DEN, 1)

        # Set homing timeout
        self._write_register(_Reg.HOMING_TIMEOUT, cfg.homing_timeout)

        # Set stall detection parameters
        self._write_register(_Reg.BLOCKING_TORQUE, cfg.blocking_torque)
        self._write_register(_Reg.BLOCKING_TIME, cfg.blocking_time)

        # Set driver polarity
        if cfg.driver_polarity != 0x00:
            self._write_register(_Reg.POLARITY, cfg.driver_polarity)

        # Configure digital inputs
        if cfg.di2_function is not None:
            self._write_register(_Reg.DI2_FUNCTION, cfg.di2_function)
            self._write_register(_Reg.DI2_LOGIC, cfg.di2_logic)

        if cfg.di3_function is not None:
            self._write_register(_Reg.DI3_FUNCTION, cfg.di3_function)
            self._write_register(_Reg.DI3_LOGIC, cfg.di3_logic)

        logger.debug("Motor parameters initialized")

    # =========================================================================
    # Enable/Disable Control
    # =========================================================================

    def enable(self) -> None:
        """
        Enable the motor (servo on).

        Transitions the motor to the Operation Enabled state, allowing motion.

        Raises:
            MotionError: If motor fails to enable or has a fault
        """
        self._check_connected()

        state = self._get_drive_state()
        logger.info(f"Enabling motor (current state: {state.value})")

        if state == DriveState.OPERATION_ENABLED:
            logger.info("Motor already enabled")
            return

        if state == DriveState.FAULT:
            raise MotionError("Motor is in fault state. Call fault_reset() first.")

        # Execute state transitions to reach Operation Enabled
        transitions = [
            (DriveState.SWITCH_ON_DISABLED, _ControlWord.CMD_SHUTDOWN),
            (DriveState.READY_TO_SWITCH_ON, _ControlWord.CMD_SWITCH_ON),
            (DriveState.SWITCHED_ON, _ControlWord.CMD_ENABLE_OPERATION),
        ]

        for target_state, control_word in transitions:
            current = self._get_drive_state()
            if current == DriveState.OPERATION_ENABLED:
                break
            self._write_register(_Reg.CONTROL_WORD, control_word)
            time.sleep(0.01)

        # Wait for Operation Enabled state
        self._wait_for_state(DriveState.OPERATION_ENABLED, self.DEFAULT_STATE_TIMEOUT)
        logger.info("Motor enabled")

        # Wait for brake release if applicable
        if self._config.has_brake and self._config.brake_release_delay_ms > 0:
            delay_s = self._config.brake_release_delay_ms / 1000.0
            logger.info(f"Waiting {delay_s}s for brake release...")
            time.sleep(delay_s)

    def disable(self) -> None:
        """
        Disable the motor (servo off).

        Transitions the motor to the Switched On state.
        """
        self._check_connected()

        state = self._get_drive_state()
        logger.info(f"Disabling motor (current state: {state.value})")

        if state in (DriveState.SWITCHED_ON, DriveState.READY_TO_SWITCH_ON, DriveState.SWITCH_ON_DISABLED):
            logger.info("Motor already disabled")
            return

        if state == DriveState.OPERATION_ENABLED:
            self._write_register(_Reg.CONTROL_WORD, _ControlWord.CMD_DISABLE_OPERATION)
            self._wait_for_state(DriveState.SWITCHED_ON, self.DEFAULT_STATE_TIMEOUT)

        logger.info("Motor disabled")

    def fault_reset(self) -> None:
        """
        Clear motor fault and return to normal operation.

        Raises:
            MotionError: If reset fails
        """
        self._check_connected()

        state = self._get_drive_state()
        if state != DriveState.FAULT:
            logger.info("Motor not in fault state")
            return

        logger.info("Resetting fault...")

        # Generate rising edge on fault reset bit
        cw = self._read_register(_Reg.CONTROL_WORD)
        self._write_register(_Reg.CONTROL_WORD, cw & ~_ControlWord.FAULT_RESET)
        time.sleep(0.01)
        self._write_register(_Reg.CONTROL_WORD, cw | _ControlWord.FAULT_RESET)
        time.sleep(0.05)
        self._write_register(_Reg.CONTROL_WORD, cw & ~_ControlWord.FAULT_RESET)

        self._wait_for_state(DriveState.SWITCH_ON_DISABLED, self.DEFAULT_STATE_TIMEOUT)
        logger.info("Fault cleared")

    # =========================================================================
    # Homing
    # =========================================================================

    def home(self, method: Optional[HomingMethod] = None, wait: bool = True) -> None:
        """
        Execute homing sequence to establish position reference.

        Args:
            method: Homing method (uses config default if None)
            wait: If True, block until homing completes

        Raises:
            MotionError: If homing fails or times out
        """
        self._check_connected()

        if method is None:
            method = self._config.homing_method

        logger.info(f"Starting homing (method: {method.name})")

        # Set homing mode
        self._write_register(_Reg.MODES_OF_OPERATION, OperationMode.HOMING)
        time.sleep(0.05)

        # Set homing method
        self._write_register(_Reg.HOMING_METHOD, method.value)

        # Set homing speeds
        cfg = self._config
        self._write_register_32bit(_Reg.HOMING_SPEED_HIGH, cfg.velocity_mm_to_pulses(cfg.homing_velocity_high))
        self._write_register_32bit(_Reg.HOMING_SPEED_LOW, cfg.velocity_mm_to_pulses(cfg.homing_velocity_low))
        self._write_register_32bit(_Reg.HOMING_ACCELERATION, cfg.velocity_mm_to_pulses(cfg.homing_acceleration))

        # Re-enable and start homing
        self._write_register(_Reg.CONTROL_WORD, _ControlWord.CMD_SHUTDOWN)
        time.sleep(0.01)
        self._write_register(_Reg.CONTROL_WORD, _ControlWord.CMD_SWITCH_ON)
        time.sleep(0.01)
        self._write_register(_Reg.CONTROL_WORD, _ControlWord.CMD_ENABLE_OPERATION)
        time.sleep(0.01)
        self._write_register(_Reg.CONTROL_WORD, 0x001F)  # Start homing

        if wait:
            self._wait_for_homing_complete()
            self._is_homed = True
            logger.info("Homing complete")

    def set_home_position(self) -> None:
        """
        Set current position as the home (zero) position.

        This does not physically move the axis.
        """
        self._check_connected()

        logger.info("Setting current position as home")
        self.home(method=HomingMethod.CURRENT_POSITION_AS_HOME, wait=True)
        self._is_homed = True

    # =========================================================================
    # Motion Control
    # =========================================================================

    def move_to(
        self,
        position_mm: float,
        velocity_mm_s: Optional[float] = None,
        wait: bool = True,
    ) -> None:
        """
        Move to an absolute position.

        Args:
            position_mm: Target position in millimeters
            velocity_mm_s: Movement velocity (uses default if None)
            wait: If True, block until motion completes

        Raises:
            MotionError: If position is out of range or motion fails
            ValueError: If position is outside stroke limits
        """
        self._check_connected()

        if not self._config.is_position_valid(position_mm):
            raise ValueError(
                f"Position {position_mm}mm outside stroke range "
                f"[{self._config.stroke_min}, {self._config.stroke_max}]"
            )

        position_pulses = self._config.mm_to_pulses(position_mm)

        if velocity_mm_s is None:
            velocity_mm_s = self._config.default_velocity
        velocity_pulses = self._config.velocity_mm_to_pulses(velocity_mm_s)

        logger.info(f"Moving to {position_mm}mm at {velocity_mm_s}mm/s")

        # Set position mode
        self._write_register(_Reg.MODES_OF_OPERATION, OperationMode.PROFILE_POSITION)

        # Set velocity
        self._write_register_32bit(_Reg.PROFILE_VELOCITY, velocity_pulses)

        # Set target position
        self._write_register_32bit(_Reg.TARGET_POSITION, position_pulses, signed=True)

        # Trigger absolute move
        cw = self._read_register(_Reg.CONTROL_WORD)
        cw &= ~_ControlWord.ABS_REL  # Absolute
        cw &= ~_ControlWord.NEW_SET_POINT
        cw &= ~_ControlWord.HALT
        self._write_register(_Reg.CONTROL_WORD, cw)
        time.sleep(0.001)
        cw |= _ControlWord.NEW_SET_POINT
        self._write_register(_Reg.CONTROL_WORD, cw)

        if wait:
            self._wait_for_motion_complete()

    def move_by(
        self,
        distance_mm: float,
        velocity_mm_s: Optional[float] = None,
        wait: bool = True,
    ) -> None:
        """
        Move by a relative distance.

        Args:
            distance_mm: Distance to move (positive or negative)
            velocity_mm_s: Movement velocity (uses default if None)
            wait: If True, block until motion completes

        Raises:
            MotionError: If motion fails
            ValueError: If target position would be outside stroke limits
        """
        self._check_connected()

        current_pos = self.get_position()
        target_pos = current_pos + distance_mm

        if not self._config.is_position_valid(target_pos):
            raise ValueError(
                f"Target position {target_pos}mm outside stroke range "
                f"[{self._config.stroke_min}, {self._config.stroke_max}]"
            )

        distance_pulses = self._config.mm_to_pulses(distance_mm)

        if velocity_mm_s is None:
            velocity_mm_s = self._config.default_velocity
        velocity_pulses = self._config.velocity_mm_to_pulses(velocity_mm_s)

        logger.info(f"Moving by {distance_mm}mm at {velocity_mm_s}mm/s")

        # Set position mode
        self._write_register(_Reg.MODES_OF_OPERATION, OperationMode.PROFILE_POSITION)

        # Set velocity
        self._write_register_32bit(_Reg.PROFILE_VELOCITY, velocity_pulses)

        # Set target distance
        self._write_register_32bit(_Reg.TARGET_POSITION, distance_pulses, signed=True)

        # Trigger relative move
        cw = self._read_register(_Reg.CONTROL_WORD)
        cw |= _ControlWord.ABS_REL  # Relative
        cw &= ~_ControlWord.NEW_SET_POINT
        cw &= ~_ControlWord.HALT
        self._write_register(_Reg.CONTROL_WORD, cw)
        time.sleep(0.001)
        cw |= _ControlWord.NEW_SET_POINT
        self._write_register(_Reg.CONTROL_WORD, cw)

        if wait:
            self._wait_for_motion_complete()

    def stop(self, wait: bool = True) -> None:
        """
        Stop current motion immediately.

        Args:
            wait: If True, block until axis has stopped
        """
        self._check_connected()

        logger.info("Stopping motion")

        # Read current position
        current_pos = self._read_register_32bit(_Reg.POSITION_ACTUAL, signed=True)

        # Set target to current position
        self._write_register_32bit(_Reg.TARGET_POSITION, current_pos, signed=True)

        # Set halt bit
        self._write_register(_Reg.CONTROL_WORD, 0x010F)

        if wait:
            start = time.time()
            while time.time() - start < 5.0:
                velocity = self._read_register_32bit(_Reg.VELOCITY_ACTUAL, signed=True)
                if abs(velocity) < 10:
                    break
                time.sleep(self.POLL_INTERVAL)

            # Update target to stopped position and clear halt
            final_pos = self._read_register_32bit(_Reg.POSITION_ACTUAL, signed=True)
            self._write_register_32bit(_Reg.TARGET_POSITION, final_pos, signed=True)
            self._write_register(_Reg.CONTROL_WORD, 0x000F)

        logger.info("Motion stopped")

    def quick_stop(self) -> None:
        """Execute emergency quick stop."""
        self._check_connected()
        logger.warning("Quick stop activated")
        self._write_register(_Reg.CONTROL_WORD, _ControlWord.CMD_QUICK_STOP)

    # =========================================================================
    # Status Reading
    # =========================================================================

    def get_position(self) -> float:
        """
        Get current position in millimeters.

        Returns:
            Current position in mm
        """
        self._check_connected()
        position_pulses = self._read_register_32bit(_Reg.POSITION_ACTUAL, signed=True)
        return self._config.pulses_to_mm(position_pulses)

    def get_velocity(self) -> float:
        """
        Get current velocity in mm/s.

        Returns:
            Current velocity in mm/s
        """
        self._check_connected()
        velocity_pulses = self._read_register_32bit(_Reg.VELOCITY_ACTUAL, signed=True)
        return self._config.velocity_pulses_to_mm(velocity_pulses)

    def is_enabled(self) -> bool:
        """Check if motor is enabled (Operation Enabled state)."""
        self._check_connected()
        return self._get_drive_state() == DriveState.OPERATION_ENABLED

    def is_moving(self) -> bool:
        """Check if axis is currently in motion."""
        self._check_connected()
        status = self._read_status_word()
        target_reached = bool(status & _StatusWord.TARGET_REACHED)
        return not target_reached

    def has_fault(self) -> bool:
        """Check if motor has a fault condition."""
        self._check_connected()
        status = self._read_status_word()
        return bool(status & _StatusWord.FAULT)

    def get_error_code(self) -> int:
        """Get current error code (0 = no error)."""
        self._check_connected()
        return self._read_register(_Reg.ERROR_CODE)

    def get_state(self) -> DriveState:
        """Get current drive state."""
        self._check_connected()
        return self._get_drive_state()

    # =========================================================================
    # Internal Methods
    # =========================================================================

    def _check_connected(self) -> None:
        if not self.is_connected:
            raise CommunicationError("Not connected to motor")

    def _read_register(self, address: int) -> int:
        return self._client.read_register(self._slave_id, address)

    def _read_register_32bit(self, address: int, signed: bool = False) -> int:
        return self._client.read_register_32bit(self._slave_id, address, signed)

    def _write_register(self, address: int, value: int) -> None:
        self._client.write_register(self._slave_id, address, value)

    def _write_register_32bit(self, address: int, value: int, signed: bool = False) -> None:
        self._client.write_register_32bit(self._slave_id, address, value, signed)

    def _read_status_word(self) -> int:
        return self._read_register(_Reg.STATUS_WORD)

    def _get_drive_state(self) -> DriveState:
        status = self._read_status_word()
        return _decode_drive_state(status)

    def _wait_for_state(self, target_state: DriveState, timeout: float) -> None:
        start = time.time()
        while time.time() - start < timeout:
            state = self._get_drive_state()
            if state == target_state:
                return
            if state == DriveState.FAULT:
                error = self.get_error_code()
                raise MotionError(f"Motor fault during state transition: error code 0x{error:04X}")
            time.sleep(self.POLL_INTERVAL)
        raise MotionError(f"Timeout waiting for state {target_state.value}")

    def _wait_for_motion_complete(self) -> None:
        start = time.time()
        while time.time() - start < self._motion_timeout:
            status = self._read_status_word()

            if status & _StatusWord.FAULT:
                error = self.get_error_code()
                raise MotionError(f"Motor fault during motion: error code 0x{error:04X}")

            if status & _StatusWord.TARGET_REACHED:
                logger.debug("Motion complete")
                return

            time.sleep(self.POLL_INTERVAL)

        raise MotionError(f"Motion timeout after {self._motion_timeout}s")

    def _wait_for_homing_complete(self) -> None:
        timeout = self._config.homing_timeout / 1000.0 + 5.0
        start = time.time()

        while time.time() - start < timeout:
            status = self._read_status_word()

            if status & _StatusWord.FAULT:
                error = self.get_error_code()
                raise MotionError(f"Motor fault during homing: error code 0x{error:04X}")

            if status & _StatusWord.TARGET_REACHED:
                mode = self._read_register(_Reg.MODES_OF_OPERATION_DISPLAY)
                if mode == OperationMode.HOMING:
                    return

            time.sleep(self.POLL_INTERVAL)

        raise MotionError(f"Homing timeout after {timeout}s")

    # =========================================================================
    # Context Manager Support
    # =========================================================================

    def __enter__(self) -> "LinearAxis":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.is_enabled():
            try:
                self.disable()
            except Exception:
                pass
        self.disconnect()

    def __repr__(self) -> str:
        status = "connected" if self.is_connected else "disconnected"
        return f"LinearAxis({self._port}, slave={self._slave_id}, {status})"


# =============================================================================
# Simulation Class
# =============================================================================

class LinearAxisSimulation:
    """
    Simulated linear axis for testing without hardware.

    Provides the same interface as LinearAxis but simulates motion.
    """

    def __init__(
        self,
        port: str = "SIM",
        slave_id: int = 1,
        baudrate: int = 115200,
        config: Optional[AxisConfig] = None,
    ):
        self._config = config or AxisConfig()
        self._position_mm = 0.0
        self._is_enabled = False
        self._is_homed = False
        self._is_connected = False
        self._is_moving = False
        self._has_fault = False

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def is_homed(self) -> bool:
        return self._is_homed

    @property
    def config(self) -> AxisConfig:
        return self._config

    def connect(self) -> None:
        self._is_connected = True
        print("Simulated linear axis connected.")

    def disconnect(self) -> None:
        self._is_connected = False
        self._is_homed = False

    def enable(self) -> None:
        self._is_enabled = True

    def disable(self) -> None:
        self._is_enabled = False

    def fault_reset(self) -> None:
        self._has_fault = False

    def home(self, method: Optional[HomingMethod] = None, wait: bool = True) -> None:
        if wait:
            time.sleep(2.0)
        self._position_mm = 0.0
        self._is_homed = True

    def set_home_position(self) -> None:
        self._position_mm = 0.0
        self._is_homed = True

    def move_to(
        self,
        position_mm: float,
        velocity_mm_s: Optional[float] = None,
        wait: bool = True,
    ) -> None:
        if not self._config.is_position_valid(position_mm):
            raise ValueError(f"Position {position_mm}mm outside stroke range")

        if wait:
            distance = abs(position_mm - self._position_mm)
            velocity = velocity_mm_s or self._config.default_velocity
            move_time = distance / velocity
            time.sleep(min(move_time, 2.0))

        self._position_mm = position_mm

    def move_by(
        self,
        distance_mm: float,
        velocity_mm_s: Optional[float] = None,
        wait: bool = True,
    ) -> None:
        target = self._position_mm + distance_mm
        self.move_to(target, velocity_mm_s, wait)

    def stop(self, wait: bool = True) -> None:
        self._is_moving = False

    def quick_stop(self) -> None:
        self._is_moving = False

    def get_position(self) -> float:
        return self._position_mm

    def get_velocity(self) -> float:
        return 0.0 if not self._is_moving else self._config.default_velocity

    def is_enabled(self) -> bool:
        return self._is_enabled

    def is_moving(self) -> bool:
        return self._is_moving

    def has_fault(self) -> bool:
        return self._has_fault

    def get_error_code(self) -> int:
        return 0

    def get_state(self) -> DriveState:
        if self._has_fault:
            return DriveState.FAULT
        if self._is_enabled:
            return DriveState.OPERATION_ENABLED
        return DriveState.SWITCH_ON_DISABLED

    def __enter__(self) -> "LinearAxisSimulation":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()

    def __repr__(self) -> str:
        return f"LinearAxisSimulation(position={self._position_mm}mm)"
