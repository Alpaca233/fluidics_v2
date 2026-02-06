#!/usr/bin/env python3
"""
Test script for PeristalticPump controller.

Run with simulation:
    python test_peristaltic_pump.py --sim

Run with real hardware:
    python test_peristaltic_pump.py --port /dev/ttyUSB0 --address 1

Test multiple pumps:
    python test_peristaltic_pump.py --port /dev/ttyUSB0 --addresses 1,2
"""

import argparse
import logging
import sys
import time

from peristaltic_pump import (
    PeristalticPump,
    PeristalticPumpSimulation,
    PumpBus,
    PumpConfig,
    Direction,
    PumpError,
    CommunicationError,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_peristaltic_pump")


def create_test_config() -> PumpConfig:
    """Create a test configuration."""
    return PumpConfig(
        max_speed_rpm=150.0,
        min_speed_rpm=0.1,
        default_speed_rpm=60.0,
        default_accel_ms=100,
        default_decel_ms=100,
        ml_per_revolution=0.5,  # Example calibration value
    )


def test_connection(pump):
    """Test connection and basic communication."""
    print("\n" + "=" * 60)
    print("TEST: Connection")
    print("=" * 60)

    print(f"Pump: {pump}")
    print(f"Connected: {pump.is_connected}")
    print(f"Address: {pump.address}")

    status = pump.get_status()
    print(f"Status register: 0x{status:04X}")

    print(f"Is running: {pump.is_running()}")
    print(f"Has alarm: {pump.has_alarm()}")
    print(f"Is released: {pump.is_released()}")

    if pump.has_alarm():
        print("Clearing alarm...")
        pump.clear_alarm()

    print("Connection test: PASSED")


def test_speed_control(pump):
    """Test speed setting."""
    print("\n" + "=" * 60)
    print("TEST: Speed Control")
    print("=" * 60)

    # Test setting speed
    print("\nSetting speed to 60 RPM...")
    pump.set_speed(60.0)
    print(f"Speed setting: {pump.speed_rpm} RPM")
    print(f"Direction: {pump.direction.name}")
    assert pump.speed_rpm == 60.0, "Speed should be 60 RPM"

    # Test negative speed (counter-clockwise)
    print("\nSetting speed to -30 RPM (counter-clockwise)...")
    pump.set_speed(-30.0)
    print(f"Speed setting: {pump.speed_rpm} RPM")
    print(f"Direction: {pump.direction.name}")
    assert pump.speed_rpm == 30.0, "Speed magnitude should be 30 RPM"
    assert pump.direction == Direction.COUNTER_CLOCKWISE, "Direction should be CCW"

    # Test direction change
    print("\nChanging direction to clockwise...")
    pump.set_direction(Direction.CLOCKWISE)
    print(f"Direction: {pump.direction.name}")
    assert pump.direction == Direction.CLOCKWISE, "Direction should be CW"

    # Test speed limit
    print("\nTesting speed limit...")
    try:
        pump.set_speed(200.0)  # Exceeds max
        print("ERROR: Should have raised ValueError")
        assert False
    except ValueError as e:
        print(f"Correctly raised ValueError: {e}")

    print("Speed control test: PASSED")


def test_start_stop(pump):
    """Test start and stop operations."""
    print("\n" + "=" * 60)
    print("TEST: Start/Stop")
    print("=" * 60)

    pump.set_speed(30.0)

    print("\nStarting pump...")
    pump.start()
    time.sleep(0.5)

    running = pump.is_running()
    print(f"Is running (hardware): {running}")

    print("\nStopping pump...")
    pump.stop()
    time.sleep(0.3)

    running = pump.is_running()
    print(f"Is running after stop: {running}")

    print("Start/Stop test: PASSED")


def test_timed_run(pump):
    """Test timed run operation."""
    print("\n" + "=" * 60)
    print("TEST: Timed Run")
    print("=" * 60)

    # Blocking run
    print("\nRunning for 2 seconds at 45 RPM (blocking)...")
    start = time.time()
    pump.run_for_time(2.0, speed_rpm=45.0, wait=True)
    elapsed = time.time() - start
    print(f"Completed in {elapsed:.2f}s")
    assert elapsed >= 1.9, "Should have taken at least 2 seconds"

    # Non-blocking run
    print("\nRunning for 2 seconds (non-blocking)...")
    thread = pump.run_for_time(2.0, speed_rpm=30.0, wait=False)
    print("Doing other work while pump runs...")
    time.sleep(0.5)
    print(f"Is running: {pump.is_running()}")
    if thread:
        thread.join()
    print("Completed")

    print("Timed run test: PASSED")


def test_direction(pump):
    """Test direction control."""
    print("\n" + "=" * 60)
    print("TEST: Direction Control")
    print("=" * 60)

    pump.set_speed(40.0)

    print("\nRunning clockwise for 1 second...")
    pump.run_for_time(1.0, direction=Direction.CLOCKWISE, wait=True)
    print(f"Direction after: {pump.direction.name}")

    print("\nRunning counter-clockwise for 1 second...")
    pump.run_for_time(1.0, direction=Direction.COUNTER_CLOCKWISE, wait=True)
    print(f"Direction after: {pump.direction.name}")

    print("Direction test: PASSED")


def test_emergency_stop(pump):
    """Test emergency stop."""
    print("\n" + "=" * 60)
    print("TEST: Emergency Stop")
    print("=" * 60)

    print("\nStarting pump at 60 RPM...")
    pump.set_speed(60.0)
    pump.start()
    time.sleep(0.3)
    print(f"Is running: {pump.is_running()}")

    print("\nEmergency stop...")
    pump.emergency_stop()
    print(f"Is running after e-stop: {pump.is_running()}")

    print("Emergency stop test: PASSED")


def test_acceleration(pump):
    """Test acceleration settings."""
    print("\n" + "=" * 60)
    print("TEST: Acceleration")
    print("=" * 60)

    print("\nSetting acceleration to 500ms, deceleration to 300ms...")
    pump.set_acceleration(accel_ms=500, decel_ms=300)

    print("\nRunning with slow acceleration...")
    pump.set_speed(60.0)
    pump.start()
    time.sleep(1.0)
    pump.stop()
    time.sleep(0.5)

    print("Acceleration test: PASSED")


def test_enable_release(pump):
    """Test enable/release (motor lock/unlock)."""
    print("\n" + "=" * 60)
    print("TEST: Enable/Release")
    print("=" * 60)

    print("\nReleasing motor...")
    pump.release()
    print(f"Is released: {pump.is_released()}")

    print("\nEnabling motor...")
    pump.enable()
    print(f"Is released: {pump.is_released()}")

    print("Enable/Release test: PASSED")


def test_calibrated_dispense(pump):
    """Test calibrated volume dispensing."""
    print("\n" + "=" * 60)
    print("TEST: Calibrated Dispense")
    print("=" * 60)

    if pump.config.ml_per_revolution <= 0:
        print("Pump not calibrated, skipping...")
        return

    print(f"Calibration: {pump.config.ml_per_revolution} mL/revolution")

    print("\nDispensing 1 mL at default speed...")
    start = time.time()
    pump.dispense_volume(1.0, wait=True)
    elapsed = time.time() - start
    print(f"Completed in {elapsed:.2f}s")

    print("\nDispensing 0.5 mL at 30 RPM...")
    start = time.time()
    pump.dispense_volume(0.5, speed_rpm=30.0, wait=True)
    elapsed = time.time() - start
    print(f"Completed in {elapsed:.2f}s")

    print("Calibrated dispense test: PASSED")


def run_all_tests(pump):
    """Run all tests."""
    tests = [
        ("Connection", test_connection),
        ("Speed Control", test_speed_control),
        ("Start/Stop", test_start_stop),
        ("Timed Run", test_timed_run),
        ("Direction", test_direction),
        ("Emergency Stop", test_emergency_stop),
        ("Acceleration", test_acceleration),
        ("Enable/Release", test_enable_release),
        ("Calibrated Dispense", test_calibrated_dispense),
    ]

    results = []
    for name, test_func in tests:
        try:
            test_func(pump)
            results.append((name, "PASSED", None))
        except AssertionError as e:
            results.append((name, "FAILED", str(e)))
            logger.error(f"Test {name} FAILED: {e}")
        except Exception as e:
            results.append((name, "ERROR", str(e)))
            logger.error(f"Test {name} ERROR: {e}")

    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, status, _ in results if status == "PASSED")
    failed = sum(1 for _, status, _ in results if status == "FAILED")
    errors = sum(1 for _, status, _ in results if status == "ERROR")

    for name, status, error in results:
        status_str = f"[{status}]"
        if error:
            print(f"  {status_str:10} {name}: {error}")
        else:
            print(f"  {status_str:10} {name}")

    print("-" * 60)
    print(f"Total: {len(results)}, Passed: {passed}, Failed: {failed}, Errors: {errors}")

    return failed == 0 and errors == 0


def test_multi_pump(bus: PumpBus, addresses: list):
    """Test multiple pumps on a bus."""
    print("\n" + "=" * 60)
    print("MULTI-PUMP TEST")
    print("=" * 60)

    pumps = [bus.get_pump(addr) for addr in addresses]

    # Test each pump
    for pump in pumps:
        print(f"\n--- Pump {pump.address} ---")
        try:
            test_connection(pump)
            test_speed_control(pump)
        except Exception as e:
            print(f"Error testing pump {pump.address}: {e}")

    # Test simultaneous operation
    print("\n" + "-" * 60)
    print("SIMULTANEOUS OPERATION")
    print("-" * 60)

    print("\nSetting different speeds...")
    for i, pump in enumerate(pumps):
        speed = 30 + (i * 20)
        pump.set_speed(speed)
        print(f"  Pump {pump.address}: {speed} RPM")

    print("\nStarting all pumps...")
    for pump in pumps:
        pump.start()

    time.sleep(2)

    print("\nStopping all pumps...")
    bus.stop_all()

    print("\nMulti-pump test completed!")


def interactive_mode(pump):
    """Interactive control mode."""
    print("\n" + "=" * 60)
    print("INTERACTIVE MODE")
    print("=" * 60)
    print("Commands:")
    print("  speed <rpm>     - Set speed (negative for reverse)")
    print("  start           - Start pump")
    print("  stop            - Stop pump")
    print("  estop           - Emergency stop")
    print("  cw              - Set direction clockwise")
    print("  ccw             - Set direction counter-clockwise")
    print("  run <sec>       - Run for duration")
    print("  dispense <mL>   - Dispense volume (if calibrated)")
    print("  accel <ms>      - Set acceleration time")
    print("  enable          - Enable motor")
    print("  release         - Release motor")
    print("  status          - Show current status")
    print("  clear           - Clear alarm")
    print("  quit            - Exit")
    print("-" * 60)

    while True:
        try:
            cmd = input(f"\npump[{pump.address}]> ").strip().lower()

            if not cmd:
                continue

            parts = cmd.split()
            action = parts[0]

            if action in ("quit", "exit", "q"):
                pump.stop()
                break

            elif action == "speed":
                if len(parts) < 2:
                    print("Usage: speed <rpm>")
                    continue
                rpm = float(parts[1])
                pump.set_speed(rpm)
                print(f"Speed set to {rpm} RPM")

            elif action == "start":
                pump.start()
                print("Pump started")

            elif action == "stop":
                pump.stop()
                print("Pump stopped")

            elif action == "estop":
                pump.emergency_stop()
                print("Emergency stop!")

            elif action == "cw":
                pump.set_direction(Direction.CLOCKWISE)
                print("Direction: Clockwise")

            elif action == "ccw":
                pump.set_direction(Direction.COUNTER_CLOCKWISE)
                print("Direction: Counter-clockwise")

            elif action == "run":
                if len(parts) < 2:
                    print("Usage: run <seconds>")
                    continue
                duration = float(parts[1])
                print(f"Running for {duration} seconds...")
                pump.run_for_time(duration, wait=True)
                print("Done")

            elif action == "dispense":
                if len(parts) < 2:
                    print("Usage: dispense <mL>")
                    continue
                volume = float(parts[1])
                print(f"Dispensing {volume} mL...")
                try:
                    pump.dispense_volume(volume, wait=True)
                    print("Done")
                except ValueError as e:
                    print(f"Error: {e}")

            elif action == "accel":
                if len(parts) < 2:
                    print("Usage: accel <ms> [decel_ms]")
                    continue
                accel = int(parts[1])
                decel = int(parts[2]) if len(parts) > 2 else accel
                pump.set_acceleration(accel, decel)
                print(f"Acceleration: {accel}ms, Deceleration: {decel}ms")

            elif action == "enable":
                pump.enable()
                print("Motor enabled")

            elif action == "release":
                pump.release()
                print("Motor released")

            elif action == "status":
                print(f"  Speed setting: {pump.speed_rpm} RPM")
                print(f"  Direction: {pump.direction.name}")
                print(f"  Current speed: {pump.get_current_speed():.1f} RPM")
                print(f"  Is running: {pump.is_running()}")
                print(f"  Has alarm: {pump.has_alarm()}")
                print(f"  Is released: {pump.is_released()}")

            elif action == "clear":
                pump.clear_alarm()
                print("Alarm cleared")

            else:
                print(f"Unknown command: {action}")

        except KeyboardInterrupt:
            print("\nInterrupted, stopping pump...")
            pump.stop()
            break
        except Exception as e:
            print(f"Error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Test PeristalticPump controller")
    parser.add_argument("--sim", action="store_true", help="Use simulation mode")
    parser.add_argument("--port", type=str, default="/dev/ttyUSB0", help="Serial port")
    parser.add_argument("--address", type=int, default=1, help="Modbus slave address")
    parser.add_argument("--addresses", type=str, help="Comma-separated addresses for multi-pump test")
    parser.add_argument("--baudrate", type=int, default=115200, help="Baud rate")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    parser.add_argument("--test", "-t", type=str, help="Run specific test")
    args = parser.parse_args()

    config = create_test_config()

    # Multi-pump test
    if args.addresses and not args.sim:
        addresses = [int(a.strip()) for a in args.addresses.split(",")]
        with PumpBus(port=args.port, baudrate=args.baudrate) as bus:
            test_multi_pump(bus, addresses)
        return

    # Single pump test
    if args.sim:
        print("Using SIMULATION mode")
        pump = PeristalticPumpSimulation(config=config)
    else:
        print(f"Using HARDWARE mode: {args.port}, address {args.address}")
        pump = PeristalticPump(
            port=args.port,
            address=args.address,
            baudrate=args.baudrate,
            config=config,
        )

    try:
        pump.connect()

        if args.interactive:
            interactive_mode(pump)
        elif args.test:
            test_map = {
                "connection": test_connection,
                "speed": test_speed_control,
                "startstop": test_start_stop,
                "timed": test_timed_run,
                "direction": test_direction,
                "estop": test_emergency_stop,
                "accel": test_acceleration,
                "enable": test_enable_release,
                "dispense": test_calibrated_dispense,
            }
            test_func = test_map.get(args.test.lower())
            if test_func:
                test_func(pump)
            else:
                print(f"Unknown test: {args.test}")
                print(f"Available tests: {', '.join(test_map.keys())}")
                sys.exit(1)
        else:
            success = run_all_tests(pump)
            sys.exit(0 if success else 1)

    except CommunicationError as e:
        logger.error(f"Communication error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(130)
    finally:
        if pump.is_connected:
            try:
                pump.stop()
            except Exception:
                pass
            pump.disconnect()


if __name__ == "__main__":
    main()
