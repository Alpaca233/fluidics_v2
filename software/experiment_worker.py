from qtpy.QtCore import QThread, Signal as pyqtSignal
import time
import pandas as pd

class ExperimentWorker(QThread):
    progress = pyqtSignal(int, int, str)
    error = pyqtSignal(str)
    finished = pyqtSignal()
    estimate = pyqtSignal(float, int)

    def __init__(self, experiment_ops, df, config):
        super().__init__()

        self.experiment_ops = experiment_ops
        self.sequences = df
        self.config = config
        self.time_to_finish, self.n_sequences = self.get_time_to_finish()
        self.estimate.emit(self.time_to_finish, self.n_sequences)

        self.abort_requested = False

    def get_time_to_finish(self):
        total_time = 0
        total_sequences = 0

        for index, seq in self.sequences.iterrows():
            t = seq['volume'] / seq['flow_rate'] * 60
            if seq['fill_tubing_with']:
                t += self.config['selector_valves']['tubing_fluid_amount_ul'] / seq['flow_rate'] * 60 + 1
            t += seq['incubation_time'] * 60
            t += 2      # Time for opening selector valve port
            t = t * seq['repeat']

            total_time += t
            total_sequences += seq['repeat']

        return total_time, total_sequences

    def wait_for_incubation(self, time_minutes):
        total_time = time_minutes * 60  # Convert minutes to seconds
        for i in range(total_time):
            time.sleep(1)
            if i % 5 == 0:  # Check abort every 5 seconds during incubation
                self._check_abort()

    def abort(self):
        self.abort_requested = True

    def _check_abort(self):
        if self.abort_requested:
            self.abort_requested = False
            raise AbortRequested()

    def run(self):
        current_sequence = 1
        try:
            for index, seq in self.sequences.iterrows():
                for _ in range(seq['repeat']):
                    try:
                        current_sequence += 1
                        self.progress.emit(index, current_sequence, "Started")
                        self.experiment_ops.process_sequence(seq)
                        if seq['incubation_time'] > 0:
                            self.progress.emit(index, current_sequence, "Incubating")
                            self.wait_for_incubation(seq['incubation_time'])
                        self.progress.emit(index, current_sequence, "Completed")
                    except AbortRequested:
                        self.error.emit("Operation aborted by user")
                    except Exception as e:
                        self.error.emit(f"Error processing sequence {index} (repeat {repeat + 1}): {str(e)}")

        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()

class AbortRequested(Exception):
    pass

class OperationError(Exception):
    pass