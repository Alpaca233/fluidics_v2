# Fluidics v2

Automated liquid handling system for microfluidics experiments. Supports MERFISH flow cell and open chamber workflows with syringe pump, selector valves, disc pump, and sensor feedback.

## Hardware

- **Microcontroller:** Teensy 4.1
- **Syringe pump:** Tecan XCalibur (via serial)
- **Selector valves:** RheoLink rotary valves (I2C, up to 5 cascaded)
- **Disc pump:** TTP peristaltic pump (UART)
- **Sensors:** SLF3X flow sensor (I2C), SSCX pressure sensors (SPI), OPX350 bubble detectors
- **Solenoid valves:** NXP33996 driver (SPI)
- **Temperature controller:** Yexian M207 TCM (optional)

## Getting Started

### Firmware

Requires [PlatformIO](https://platformio.org/).

```bash
cd firmware
pio run                # Build
pio run -t upload      # Upload to Teensy 4.1
```

### Software

Requires Python 3 with: PyQt5, pandas, matplotlib, pyserial, cobs, numpy.

**1. Find serial numbers for connected devices:**

```bash
cd software
python list_controllers.py
```

**2. Create a configuration file** based on the examples in `sample_config/`:

- `MERFISH_config.json` — MERFISH flow cell setup
- `open_chamber_config.json` — Open chamber setup

Key fields to set:
- `microcontroller.serial_number` — Teensy serial number
- `syringe_pump.serial_number` — Syringe pump serial number
- `syringe_pump.volume_ul` — Syringe volume (e.g. 2500 or 5000)
- `syringe_pump.speed_code_limit` — Maximum speed code (lower = faster, range 1-40)
- `selector_valves.valve_ids_allowed` — IDs of connected selector valves (e.g. `[0, 1, 2]`)
- `selector_valves.number_of_ports` — Number of ports per valve
- `selector_valves.reagent_name_mapping` — Port-to-reagent labels (shown in GUI)
- `selector_valves.tubing_fluid_amount_to_valve_ul` — Tubing dead volume from selector valve to syringe pump
- `selector_valves.tubing_fluid_amount_to_port_ul` — Tubing dead volume from reagent to selector valve port
- `application` — `"MERFISH"` or `"Open Chamber"`

Open chamber configs additionally require:
- `chamber_volume_ul` — Chamber volume
- `tubing_fluid_amount_sv_to_sp_ul` — Tubing volume: selector valve to syringe pump
- `tubing_fluid_amount_sp_to_oc_ul` — Tubing volume: syringe pump to open chamber

**3. Launch the GUI:**

```bash
python gui.py --config path/to/config.json
```

Or run sequences from the command line:

```bash
python run_sequences.py --path path/to/sequences.csv --config path/to/config.json
```

Use `--simulation` to run without connected hardware.

## Experiment Sequences

Experiments are defined as CSV files with the following columns:

| Column | Description |
|--------|-------------|
| `sequence_name` | Operation to perform (see below) |
| `fluidic_port` | Selector valve port number |
| `flow_rate` | Flow rate in uL/min |
| `volume` | Volume in uL |
| `incubation_time` | Wait time in minutes after the operation |
| `repeat` | Number of times to repeat this row |
| `fill_tubing_with` | Port to refill tubing from after operation (0 = disable) |
| `include` | 1 to include, 0 to skip |

### MERFISH Sequence Names

| Name | Description |
|------|-------------|
| `Flow <name>` | Flow reagent from the specified port |
| `Priming` | Prime all tubings with corresponding reagents |
| `Clean Up` | Flush all tubings (typically with water) |

### Open Chamber Sequence Names

| Name | Description |
|------|-------------|
| `Add Reagent` | Dispense reagent into chamber (tubings already filled) |
| `Clear Tubings and Add Reagent` | Clear previous liquid from tubings, then dispense reagent |
| `Wash with Constant Flow` | Flow reagent while aspirating with disc pump |
| `Priming` | Prime all tubings |
| `Clean Up` | Flush all tubings and aspirate chamber |
| `Set Temperature <value>` | Set temperature controller to target (e.g. `Set Temperature 50`) |

## Communication Protocol

The firmware and software communicate over serial at 2,000,000 baud using COBS framing. Commands are fixed at 15 bytes, responses at 30 bytes. The command definitions in `firmware/_defs.h` and `software/fluidics/control/_def.py` must be kept in sync.
