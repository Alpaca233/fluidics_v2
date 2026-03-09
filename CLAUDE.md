# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Fluidics v2 is a microfluidics control system for automated liquid handling experiments (MERFISH, open chamber). It consists of two subsystems:

- **`firmware/`** — Teensy 4.1 C++/Arduino firmware that drives hardware (pumps, valves, sensors)
- **`software/`** — Python control software with PyQt5 GUI and CLI for experiment automation

## Build & Run Commands

### Firmware (PlatformIO)

```bash
cd firmware
pio run                    # Build firmware
pio run -t upload          # Build and upload to Teensy 4.1
pio device monitor         # Serial monitor (2000000 baud)
```

Source files are in `firmware/` root (not `src/`), configured via `platformio.ini` with `src_dir = .`.

### Software (Python)

```bash
cd software
python gui.py                                          # Launch GUI
python run_sequences.py --path <csv> --config <json>   # Run sequences from CLI
python list_controllers.py                             # Discover serial devices
python run_sequences.py --path sample_sequences/merfish-experiment.csv --config sample_config/MERFISH_config.json --simulation  # Simulation mode (no hardware)
```

**Python dependencies:** PyQt5, pandas, matplotlib, pyserial, cobs, numpy

### Tests

```bash
cd software
python tests/startup.py    # Initialization/control loop test
python tests/demo.py       # Interactive hardware demo
```

Tests are hardware-oriented scripts, not a standard test framework. Use `--simulation` flag on `run_sequences.py` for software-only testing.

## Architecture

### Communication Protocol

The firmware and software communicate over serial at 2,000,000 baud using COBS (Consistent Overhead Byte Stuffing) framing via the PacketSerial library. Commands are 15 bytes (`MCU_CMD_LENGTH`), responses are 30 bytes (`MCU_MSG_LENGTH`). Command IDs are mirrored between:
- **Firmware:** `_defs.h` → `SerialCommands_t` enum
- **Software:** `fluidics/control/_def.py` → `CMD_SET` class

These must stay in sync. Same applies to `VALVE_POSITIONS`/`ValvesStates_t` and `COMMAND_STATUS`/`CommandExecution_t`.

### Software Module Structure

- **`fluidics/control/controller.py`** — Core `FluidController` class wrapping serial communication; `FluidControllerSimulation` for testing without hardware
- **`fluidics/control/syringe_pump.py`** — Tecan XCalibur syringe pump control (uses `tecancavro/` submodule); has simulation class
- **`fluidics/control/selector_valve.py`** — `SelectorValveSystem` manages cascaded multi-port rotary valve routing with port-to-reagent mapping
- **`fluidics/control/temperature_controller.py`** — TCM temperature controller with CRC32 checksums; has simulation class
- **`fluidics/control/disc_pump.py`** — Peristaltic disc pump wrapper
- **`fluidics/control/_def.py`** — Shared constants (command IDs, valve positions, sensor params, PID limits)
- **`fluidics/merfish_operations.py`** — MERFISH experiment sequence logic
- **`fluidics/open_chamber_operations.py`** — Open chamber experiment sequence logic
- **`fluidics/experiment_worker.py`** — Threaded experiment execution with progress callbacks

### Firmware Module Structure

- **`controller_teensy41.ino`** — Main firmware: serial command dispatch, control loops (bang-bang and PID), state machine
- **Hardware drivers:** `NXP33996` (solenoid valves), `OPX350` (bubble sensors), `RheoLink` (rotary valves), `SLF3X` (flow sensor, I2C), `SSCX` (pressure sensors, SPI), `TTP` (disc pump, UART), `AutoPID` (PID controller)
- **`_defs.h`** — Pin assignments, sensor parameters, hardware constants

### Experiment Flow

1. Config JSON defines hardware serial numbers, valve IDs, reagent mappings
2. CSV sequences define operations: `sequence_name, fluidic_port, flow_rate, volume, incubation_time, repeat, fill_tubing_with, include`
3. `ExperimentWorker` iterates CSV rows, calling operation methods on `MERFISHOperations` or `OpenChamberOperations`
4. Operations orchestrate syringe pump, selector valves, and controller commands

### Simulation Mode

All major hardware classes have `*Simulation` counterparts. Pass `--simulation` to `run_sequences.py` or toggle in GUI to run without connected hardware.

## Key Conventions

- Firmware library dependency: `PacketSerial` for COBS encoding (declared in `platformio.ini`)
- Syringe pump uses Tecan Cavro protocol via `fluidics/control/tecancavro/` — this is a vendored library
- Config files live in `sample_config/`, sequence CSVs in `sample_sequences/`
- Hardware pin assignments are all in `firmware/_defs.h`
- The `application` field in config JSON (`"MERFISH"` or `"Open Chamber"`) selects which operations class to use
