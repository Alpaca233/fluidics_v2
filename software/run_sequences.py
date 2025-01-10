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
from merfish_operations import MERFISHOperations
#from open_chamber_operations import OpenChamberOperations
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
        '--app', required=True,
        choices=['MERFISH', 'Open Chamber'],
        help='Your application type'
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

def load_config(config_path='config.json'):
    with open(config_path, 'r') as f:
        return json.load(f)

def main():
    args = parse_args()

    try:
        # Load sequences
        df = pd.read_csv(args.path)
        df = df[df['include'] == 1]
        # Load config
        config = load_config(args.config)

        if args.simulation:
            # Initialize hardware objects
            controller = FluidController(config['microcontroller']['serial_number'])
            syringePump = SyringePump(
                            sn=config['syringe_pump']['serial_number'],
                            syringe_ul=config['syringe_pump']['volume_ul'], 
                            speed_code_limit=config['syringe_pump']['speed_code_limit'],
                            waste_port=3)
        else:
            # Initialize simulated hardware objects
            controller = FluidControllerSimulation(config['microcontroller']['serial_number'])
            syringePump = SyringePumpSimulation(
                            sn=config['syringe_pump']['serial_number'],
                            syringe_ul=config['syringe_pump']['volume_ul'], 
                            speed_code_limit=config['syringe_pump']['speed_code_limit'],
                            waste_port=3)
        controller.begin()
        controller.send_command(CMD_SET.CLEAR)
        selectorValveSystem = SelectorValveSystem(controller, config)
        if args.application == 'Open chamber':
            discPump = DiscPump(controller)

        # Run experiment
        if args.application == 'MERFISH':
            experiment_ops = MERFISHOperations(config, syringePump, selectorValveSystem)
        elif args.application == 'Open chamber':
            experiment_ops = OpenChamberOperations(config, syringePump, selectorValveSystem, discPump)
        worker = ExperimentWorker(experiment_ops, df, config)
        worker.error.connect(lambda msg: print(f"Error in running experiment: {msg}", file=sys.stderr))
        worker.finished.connect(lambda: print("Experiment completed"))
        worker.run()

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()