import argparse
import sys
import json
import time
import threading
import pandas as pd

from control.controller import FluidControllerSimulation, FluidController
from control.syringe_pump import SyringePumpSimulation, SyringePump
from control.selector_valve import SelectorValveSystem
from control.disc_pump import DiscPump
from control.temperature_controller import TCMControllerSimulation, TCMController
from merfish_operations import MERFISHOperations
from open_chamber_operations import OpenChamberOperations
from experiment_worker import ExperimentWorker
from control._def import CMD_SET


def parse_args():
    parser = argparse.ArgumentParser(
        description='Run sequences from a CSV file'
    )
    parser.add_argument(
        '--path', required=True,
        help='Path to the CSV file containing sequences'
    )
    parser.add_argument(
        '--config', default='config.json',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--simulation',
        action='store_true',
        default=False,
        help='Run in simulation mode without operating hardware'
    )
    return parser.parse_args()

def load_config(config_path='./config.json'):
    with open(config_path, 'r') as f:
        return json.load(f)

def initialize_hardware(simulation, config):
    if simulation:
        controller = FluidControllerSimulation(config['microcontroller']['serial_number'])
        syringePump = SyringePumpSimulation(
            sn=config['syringe_pump']['serial_number'],
            syringe_ul=config['syringe_pump']['volume_ul'], 
            speed_code_limit=config['syringe_pump']['speed_code_limit'],
            waste_port=3)
        if 'temperature_controller' in config and config['use_temperature_controller']:
                temperatureController = TCMControllerSimulation()
    else:
        controller = FluidController(config['microcontroller']['serial_number'])
        syringePump = SyringePump(
            sn=config['syringe_pump']['serial_number'],
            syringe_ul=config['syringe_pump']['volume_ul'], 
            speed_code_limit=config['syringe_pump']['speed_code_limit'],
            waste_port=3)
        if 'temperature_controller' in config and config['temperature_controller']['use_temperature_controller']:
                temperatureController = TCMController(config['temperature_controller']['serial_number'])

    controller.begin()
    controller.send_command(CMD_SET.CLEAR)

    return controller, syringePump

def update_progress(index, sequence_num, status):
    print(f"Sequence {index} ({sequence_num}): {status}")

def on_error(error_msg):
    print(f"Error: {error_msg}")

def on_finished():
    print("Experiment completed")

def on_estimate(time_to_finish, n_sequences):
    print(f"Estimated time: {time_to_finish}s, Sequences: {n_sequences}")

def main():
    args = parse_args()

    try:
        # Load sequences
        df = pd.read_csv(args.path)
        df = df[df['include'] == 1]
        # Load config
        config = load_config(args.config)

        controller, syringePump = initialize_hardware(args.simulation, config)

        selectorValveSystem = SelectorValveSystem(controller, config)
        if config['application'] == "Open Chamber":
            discPump = DiscPump(controller)

        # Run experiment
        if config['application'] == "MERFISH":
            experiment_ops = MERFISHOperations(config, syringePump, selectorValveSystem)
        elif config['application'] == "Open Chamber":
            experiment_ops = OpenChamberOperations(config, syringePump, selectorValveSystem, discPump)

        callbacks = {
            'update_progress': update_progress,
            'on_error': on_error,
            'on_finished': on_finished,
            'on_estimate': on_estimate
        }

        worker = ExperimentWorker(experiment_ops, df, config, callbacks)
        thread = threading.Thread(target=worker.run)
        thread.start()

        thread.join()

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if thread:
            thread.join()
        sys.exit(1)
    finally:
        syringePump.close()

if __name__ == '__main__':
    main()