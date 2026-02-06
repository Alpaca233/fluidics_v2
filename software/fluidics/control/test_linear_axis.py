#!/usr/bin/env python3
"""
Test script for LinearAxis controller.

Run with simulation:
    python test_linear_axis.py --sim

Run with real hardware:
    python test_linear_axis.py --port /dev/ttyUSB0 --slave 1
"""

import argparse
import logging
import sys
import time

from linear_axis import (
    LinearAxis,
    LinearAxisSimulation,
    AxisConfig,
    HomingMethod,
    DriveState,
    LinearAxisError,
    CommunicationError,
    MotionError,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_linear_axis")


def create_test_config() -> AxisConfig:
    """Create a test configuration."""
    return AxisConfig(
        ball_screw_lead=10.0,
        encoder_resolution=10000,
        stroke_min=0.0,
        stroke_max=100.0,
        max_velocity=100.0,
        default_velocity=50.0,
        default_acceleration=200.0,
        homing_method=HomingMethod.NEGATIVE_LIMIT_SWITCH,
        homing_velocity_high=20.0,
        homing_velocity_low=5.0,
        homing_timeout=60000,
    )


def test_connection(axis):
    """Test connection and basic communication."""
    print("\n" + "=" * 60)
    print("TEST: Connection")
    print("=" * 60)

    print(f"Axis: {axis}")
    print(f"Connected: {axis.is_connected}")

    state = axis.get_state()
    print(f"Drive state: {state.value}")

    has_fault = axis.has_fault()
    print(f"Has fault: {has_fault}")

    if has_fault:
        error_code = axis.get_error_code()
        print(f"Error code: 0x{error_code:04X}")
        print("Attempting fault reset...")
        axis.fault_reset()
        print(f"Fault after reset: {axis.has_fault()}")

    print("Connection test: PASSED")


def test_enable_disable(axis):
    """Test enabling and disabling the motor."""
    print("\n" + "=" * 60)
    print("TEST: Enable/Disable")
    print("=" * 60)

    print("Enabling motor...")
    axis.enable()
    print(f"Is enabled: {axis.is_enabled()}")
    print(f"State: {axis.get_state().value}")
    assert axis.is_enabled(), "Motor should be enabled"

    print("Disabling motor...")
    axis.disable()
    print(f"Is enabled: {axis.is_enabled()}")
    print(f"State: {axis.get_state().value}")
    assert not axis.is_enabled(), "Motor should be disabled"

    print("Enable/Disable test: PASSED")


def test_homing(axis):
    """Test homing sequence."""
    print("\n" + "=" * 60)
    print("TEST: Homing")
    print("=" * 60)

    print("Enabling motor...")
    axis.enable()

    print(f"Is homed before: {axis.is_homed}")

    print("Starting homing sequence...")
    start_time = time.time()
    axis.home()
    elapsed = time.time() - start_time
    print(f"Homing completed in {elapsed:.2f}s")

    print(f"Is homed after: {axis.is_homed}")
    assert axis.is_homed, "Axis should be homed"

    position = axis.get_position()
    print(f"Position after homing: {position:.3f} mm")

    print("Homing test: PASSED")


def test_positioning(axis):
    """Test absolute and relative positioning."""
    print("\n" + "=" * 60)
    print("TEST: Positioning")
    print("=" * 60)

    if not axis.is_enabled():
        print("Enabling motor...")
        axis.enable()

    if not axis.is_homed:
        print("Homing first...")
        axis.home()

    initial_pos = axis.get_position()
    print(f"Initial position: {initial_pos:.3f} mm")

    # Test absolute move
    target1 = 30.0
    print(f"\nMoving to absolute position: {target1} mm")
    start_time = time.time()
    axis.move_to(target1)
    elapsed = time.time() - start_time
    pos1 = axis.get_position()
    print(f"Position after move: {pos1:.3f} mm (took {elapsed:.2f}s)")
    assert abs(pos1 - target1) < 0.1, f"Position error too large: {abs(pos1 - target1)}"

    # Test relative move
    distance = 20.0
    print(f"\nMoving by relative distance: +{distance} mm")
    start_time = time.time()
    axis.move_by(distance)
    elapsed = time.time() - start_time
    pos2 = axis.get_position()
    expected = target1 + distance
    print(f"Position after move: {pos2:.3f} mm (expected: {expected} mm, took {elapsed:.2f}s)")
    assert abs(pos2 - expected) < 0.1, f"Position error too large: {abs(pos2 - expected)}"

    # Test negative relative move
    distance = -15.0
    print(f"\nMoving by relative distance: {distance} mm")
    axis.move_by(distance)
    pos3 = axis.get_position()
    expected = pos2 + distance
    print(f"Position after move: {pos3:.3f} mm (expected: {expected} mm)")
    assert abs(pos3 - expected) < 0.1, f"Position error too large: {abs(pos3 - expected)}"

    # Return to zero
    print("\nReturning to home position...")
    axis.move_to(0.0)
    pos4 = axis.get_position()
    print(f"Final position: {pos4:.3f} mm")

    print("Positioning test: PASSED")


def test_velocity_control(axis):
    """Test different velocities."""
    print("\n" + "=" * 60)
    print("TEST: Velocity Control")
    print("=" * 60)

    if not axis.is_enabled():
        axis.enable()

    if not axis.is_homed:
        axis.home()

    axis.move_to(0.0)

    # Test slow velocity
    print("\nMoving at slow velocity (10 mm/s)...")
    start_time = time.time()
    axis.move_to(20.0, velocity_mm_s=10.0)
    elapsed_slow = time.time() - start_time
    print(f"Slow move completed in {elapsed_slow:.2f}s")

    # Test fast velocity
    print("\nMoving at fast velocity (80 mm/s)...")
    start_time = time.time()
    axis.move_to(0.0, velocity_mm_s=80.0)
    elapsed_fast = time.time() - start_time
    print(f"Fast move completed in {elapsed_fast:.2f}s")

    # Fast should be quicker than slow
    print(f"\nSlow: {elapsed_slow:.2f}s, Fast: {elapsed_fast:.2f}s")
    assert elapsed_fast < elapsed_slow, "Fast move should be quicker than slow move"

    print("Velocity control test: PASSED")


def test_stop(axis):
    """Test stop functionality."""
    print("\n" + "=" * 60)
    print("TEST: Stop")
    print("=" * 60)

    if not axis.is_enabled():
        axis.enable()

    if not axis.is_homed:
        axis.home()

    axis.move_to(0.0)

    print("Starting long move (non-blocking)...")
    axis.move_to(80.0, velocity_mm_s=20.0, wait=False)

    print("Waiting 0.5s then stopping...")
    time.sleep(0.5)

    pos_before_stop = axis.get_position()
    print(f"Position before stop: {pos_before_stop:.3f} mm")

    axis.stop()
    pos_after_stop = axis.get_position()
    print(f"Position after stop: {pos_after_stop:.3f} mm")

    print(f"Is moving: {axis.is_moving()}")
    assert not axis.is_moving(), "Axis should not be moving after stop"

    # Position should have changed but not reached target
    assert pos_before_stop > 0, "Axis should have moved"
    assert pos_after_stop < 80.0, "Axis should have stopped before target"

    print("Stop test: PASSED")


def test_limits(axis):
    """Test stroke limit validation."""
    print("\n" + "=" * 60)
    print("TEST: Stroke Limits")
    print("=" * 60)

    stroke_min = axis.config.stroke_min
    stroke_max = axis.config.stroke_max
    print(f"Stroke range: [{stroke_min}, {stroke_max}] mm")

    # Test position below minimum
    try:
        print(f"\nAttempting to move to {stroke_min - 10} mm (below minimum)...")
        axis.move_to(stroke_min - 10)
        print("ERROR: Should have raised ValueError")
        assert False
    except ValueError as e:
        print(f"Correctly raised ValueError: {e}")

    # Test position above maximum
    try:
        print(f"\nAttempting to move to {stroke_max + 10} mm (above maximum)...")
        axis.move_to(stroke_max + 10)
        print("ERROR: Should have raised ValueError")
        assert False
    except ValueError as e:
        print(f"Correctly raised ValueError: {e}")

    print("Limits test: PASSED")


def test_set_home_position(axis):
    """Test setting current position as home."""
    print("\n" + "=" * 60)
    print("TEST: Set Home Position")
    print("=" * 60)

    if not axis.is_enabled():
        axis.enable()

    if not axis.is_homed:
        axis.home()

    # Move to a position
    axis.move_to(25.0)
    pos_before = axis.get_position()
    print(f"Position before set_home: {pos_before:.3f} mm")

    # Set current position as home
    print("Setting current position as home...")
    axis.set_home_position()

    pos_after = axis.get_position()
    print(f"Position after set_home: {pos_after:.3f} mm")

    # Position should now be 0 (or very close)
    assert abs(pos_after) < 0.1, f"Position should be near zero, got {pos_after}"

    print("Set home position test: PASSED")


def run_all_tests(axis):
    """Run all tests."""
    tests = [
        ("Connection", test_connection),
        ("Enable/Disable", test_enable_disable),
        ("Homing", test_homing),
        ("Positioning", test_positioning),
        ("Velocity Control", test_velocity_control),
        ("Stop", test_stop),
        ("Limits", test_limits),
        ("Set Home Position", test_set_home_position),
    ]

    results = []
    for name, test_func in tests:
        try:
            test_func(axis)
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


def interactive_test(axis):
    """Interactive testing mode."""
    print("\n" + "=" * 60)
    print("INTERACTIVE MODE")
    print("=" * 60)
    print("Commands:")
    print("  c        - connect")
    print("  d        - disconnect")
    print("  e        - enable")
    print("  x        - disable")
    print("  h        - home")
    print("  m <pos>  - move to position (mm)")
    print("  r <dist> - move by distance (mm)")
    print("  s        - stop")
    print("  p        - print position")
    print("  v        - print velocity")
    print("  t        - print state")
    print("  f        - fault reset")
    print("  q        - quit")
    print("-" * 60)

    while True:
        try:
            cmd = input("\n> ").strip().lower()

            if not cmd:
                continue

            parts = cmd.split()
            action = parts[0]

            if action == "q":
                print("Exiting...")
                break
            elif action == "c":
                axis.connect()
                print("Connected")
            elif action == "d":
                axis.disconnect()
                print("Disconnected")
            elif action == "e":
                axis.enable()
                print("Enabled")
            elif action == "x":
                axis.disable()
                print("Disabled")
            elif action == "h":
                print("Homing...")
                axis.home()
                print("Homed")
            elif action == "m":
                if len(parts) < 2:
                    print("Usage: m <position_mm>")
                    continue
                pos = float(parts[1])
                vel = float(parts[2]) if len(parts) > 2 else None
                print(f"Moving to {pos} mm...")
                axis.move_to(pos, velocity_mm_s=vel)
                print(f"Position: {axis.get_position():.3f} mm")
            elif action == "r":
                if len(parts) < 2:
                    print("Usage: r <distance_mm>")
                    continue
                dist = float(parts[1])
                vel = float(parts[2]) if len(parts) > 2 else None
                print(f"Moving by {dist} mm...")
                axis.move_by(dist, velocity_mm_s=vel)
                print(f"Position: {axis.get_position():.3f} mm")
            elif action == "s":
                axis.stop()
                print("Stopped")
            elif action == "p":
                print(f"Position: {axis.get_position():.3f} mm")
            elif action == "v":
                print(f"Velocity: {axis.get_velocity():.3f} mm/s")
            elif action == "t":
                print(f"State: {axis.get_state().value}")
                print(f"Enabled: {axis.is_enabled()}")
                print(f"Homed: {axis.is_homed}")
                print(f"Moving: {axis.is_moving()}")
                print(f"Fault: {axis.has_fault()}")
                if axis.has_fault():
                    print(f"Error code: 0x{axis.get_error_code():04X}")
            elif action == "f":
                axis.fault_reset()
                print("Fault reset")
            else:
                print(f"Unknown command: {action}")

        except KeyboardInterrupt:
            print("\nInterrupted")
            break
        except Exception as e:
            print(f"Error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Test LinearAxis controller")
    parser.add_argument("--sim", action="store_true", help="Use simulation mode")
    parser.add_argument("--port", type=str, default="/dev/ttyUSB0", help="Serial port")
    parser.add_argument("--slave", type=int, default=1, help="Modbus slave ID")
    parser.add_argument("--baudrate", type=int, default=115200, help="Baud rate")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    parser.add_argument("--test", "-t", type=str, help="Run specific test")
    args = parser.parse_args()

    config = create_test_config()

    if args.sim:
        print("Using SIMULATION mode")
        axis = LinearAxisSimulation(config=config)
    else:
        print(f"Using HARDWARE mode: {args.port}, slave {args.slave}")
        axis = LinearAxis(
            port=args.port,
            slave_id=args.slave,
            baudrate=args.baudrate,
            config=config,
        )

    try:
        axis.connect()

        if args.interactive:
            interactive_test(axis)
        elif args.test:
            # Run specific test
            test_map = {
                "connection": test_connection,
                "enable": test_enable_disable,
                "homing": test_homing,
                "positioning": test_positioning,
                "velocity": test_velocity_control,
                "stop": test_stop,
                "limits": test_limits,
                "sethome": test_set_home_position,
            }
            test_func = test_map.get(args.test.lower())
            if test_func:
                test_func(axis)
            else:
                print(f"Unknown test: {args.test}")
                print(f"Available tests: {', '.join(test_map.keys())}")
                sys.exit(1)
        else:
            # Run all tests
            success = run_all_tests(axis)
            sys.exit(0 if success else 1)

    except CommunicationError as e:
        logger.error(f"Communication error: {e}")
        sys.exit(1)
    except MotionError as e:
        logger.error(f"Motion error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(130)
    finally:
        if axis.is_connected:
            try:
                if axis.is_enabled():
                    axis.disable()
            except Exception:
                pass
            axis.disconnect()


if __name__ == "__main__":
    main()
