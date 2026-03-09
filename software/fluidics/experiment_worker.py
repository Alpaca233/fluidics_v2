import time
import threading

class ExperimentWorker:
    def __init__(self, experiment_ops, sequences, config, callbacks=None):
        """
        Initialize ExperimentWorker with callbacks instead of signals.

        Args:
            experiment_ops: The experiment operations object
            sequences: list[dict] of validated sequence dicts, each with a 'type' key
            config: Configuration object
            callbacks: Dictionary of callback functions with keys:
                - 'update_progress': fn(index, sequence_num, status)
                - 'on_error': fn(error_message)
                - 'on_finished': fn()
                - 'on_estimate': fn(time_to_finish, n_sequences)
        """

        self.experiment_ops = experiment_ops
        self.sequences = sequences
        self.config = config
        self.callbacks = callbacks or {}
        self._abort_event = threading.Event()
        self._abort_event.clear()

        self.time_to_finish, self.n_sequences = self.get_time_to_finish()
        self._call_callback('on_estimate', self.time_to_finish, self.n_sequences)

    def _call_callback(self, name, *args):
        """Safely call a callback if it exists."""
        if self.callbacks.get(name):
            self.callbacks[name](*args)

    def get_time_to_finish(self):
        total_time = 0
        total_sequences = 0
        for seq in self.sequences:
            if seq['type'] == "set_temperature":
                t = seq.get('incubation_time', 0) * 60 + 60
            else:
                t = seq.get('volume', 0) / max(seq.get('flow_rate', 1), 1) * 60
                if seq.get('fill_tubing_with'):
                    t += self.config.reagent_selection.common_tubing_fluid_amount_ul / max(seq.get('flow_rate', 1), 1) * 60 + 1
                if seq.get('incubation_time', 0) > 0:
                    t += seq['incubation_time'] * 60
                t += 2
            repeat = seq.get('repeat', 1)
            t = t * repeat
            total_time += t
            total_sequences += repeat
        return total_time, total_sequences

    def wait_for_incubation(self, time_minutes):
        total_seconds = time_minutes * 60  # Convert minutes to seconds
        if self._abort_event.wait(total_seconds):
            raise AbortRequested()

    def abort(self):
        self._abort_event.set()

    def run(self):
        current_sequence = 0
        try:
            for index, seq in enumerate(self.sequences):
                for r in range(seq.get('repeat', 1)):
                    try:
                        current_sequence += 1
                        self._call_callback('update_progress', index, current_sequence, "Started")
                        self.experiment_ops.process_sequence(seq)
                        if self._abort_event.is_set():
                            raise AbortRequested()

                        incubation_time = seq.get('incubation_time', 0)
                        if incubation_time > 0:
                            self._call_callback('update_progress', index, current_sequence, "Incubating")
                            self.wait_for_incubation(incubation_time)
                        self._call_callback('update_progress', index, current_sequence, "Completed")

                    except AbortRequested:
                        self._call_callback('on_error', "Operation aborted by user")
                        return
                    except Exception as e:
                        self._call_callback('on_error',
                            f"Error processing sequence {index} (repeat {r + 1}): {str(e)}")
                        return

        except Exception as e:
            self._call_callback('on_error', str(e))
        finally:
            self._call_callback('on_finished')

class AbortRequested(Exception):
    pass

class OperationError(Exception):
    pass