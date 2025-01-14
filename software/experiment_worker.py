import time
import pandas as pd

class ExperimentWorker:
    def __init__(self, experiment_ops, df, config, callbacks=None):
        """
        Initialize ExperimentWorker with callbacks instead of signals.
        
        Args:
            experiment_ops: The experiment operations object
            df: DataFrame containing sequences
            config: Configuration dictionary
            callbacks: Dictionary of callback functions with keys:
                - 'update_progress': fn(index, sequence_num, status)
                - 'on_error': fn(error_message)
                - 'on_finished': fn()
                - 'estimate_time': fn(time_to_finish, n_sequences)
        """

        self.experiment_ops = experiment_ops
        self.sequences = df
        self.config = config
        self.callbacks = callbacks or {}
        self.abort_requested = False

        self.time_to_finish, self.n_sequences = self.get_time_to_finish()
        self._call_callback('on_estimate', self.time_to_finish, self.n_sequences)

    def _call_callback(self, name, *args):
        """Safely call a callback if it exists."""
        if self.callbacks.get(name):
            self.callbacks[name](*args)

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
        current_sequence = 0
        try:
            for index, seq in self.sequences.iterrows():
                for _ in range(seq['repeat']):
                    try:
                        current_sequence += 1
                        self._call_callback('update_progress', index, current_sequence, "Started")
                        self.experiment_ops.process_sequence(seq)

                        if seq['incubation_time'] > 0:
                            self._call_callback('update_progress', index, current_sequence, "Incubating")
                            self.wait_for_incubation(seq['incubation_time'])
                        self._call_callback('update_progress', index, current_sequence, "Completed")

                    except AbortRequested:
                        self._call_callback('on_error', "Operation aborted by user")
                        return
                    except Exception as e:
                        self._call_callback('on_error', 
                            f"Error processing sequence {index} (repeat {repeat + 1}): {str(e)}")
                        return

        except Exception as e:
            self._call_callback('on_error', str(e))
        finally:
            self._call_callback('on_finished')

class AbortRequested(Exception):
    pass

class OperationError(Exception):
    pass