from time import sleep
from .experiment_worker import AbortRequested, OperationError

class MERFISHOperations():
    def __init__(self, config, syringe_pump, selector_valves):
        self.config = config
        self.sp = syringe_pump
        self.sv = selector_valves
        self.extract_port = self.config['syringe_pump']['extract_port']
        self.speed_code_limit = self.config['syringe_pump']['speed_code_limit']

    def process_sequence(self, sequence):
        print(sequence)
        try:
            sequence_name = sequence['sequence_name']
            port = int(sequence['fluidic_port'])
            flow_rate = int(sequence['flow_rate'])
            volume = int(sequence['volume'])
            incubation_time = int(sequence['incubation_time'])
            fill_tubing_with = sequence['fill_tubing_with']
            try:
                use_ports = sequence['use_ports']  # for use from Squid software widget
            except:
                use_ports = None
        except:
            raise ValueError("Invalid sequence")

        if sequence_name.startswith("Flow "):
            self.flow_reagent(port, flow_rate, volume, fill_tubing_with)
        elif sequence_name in ("Priming", "Clean Up"):
            self.priming_or_clean_up(port, flow_rate, volume, use_ports)
        else:
            raise ValueError(f"Unknown sequence name: {sequence_name}")

    def _empty_syringe_pump_on_full(self, volume):
        if self.sp.get_current_volume() + self.sp.get_chained_volume() + volume > 0.95 * self.config['syringe_pump']['volume_ul']:
            try:
                self.sp.dispense_to_waste()
                self.sp.execute()
            except Exception as e:
                raise OperationError(f"Failed to empty syringe pump: {str(e)}")

    def flow_reagent(self, port, flow_rate, volume, fill_tubing_with_port):
        """
        Flow reagent from {port}. Finally, fill the tubings before sample with reagent from {fill_tubing_with_port}.
        Only the ports on the last selector valve should be used for {fill_tubing_with_port}, usually a common buffer.
        """
        speed_code = self.sp.flow_rate_to_speed_code(flow_rate)
        try:
            self.sp.reset_chain()
            self._empty_syringe_pump_on_full(volume)
            self.sv.open_port(port)
            self.sp.extract(self.extract_port, volume, speed_code)
            self.sp.execute()
            if self.sp.is_aborted:
                return
            if fill_tubing_with_port:
                self.sv.open_port(int(fill_tubing_with_port))
                self._empty_syringe_pump_on_full(self.sv.get_tubing_fluid_amount_to_valve(fill_tubing_with_port))
                self.sp.extract(self.extract_port, self.sv.get_tubing_fluid_amount_to_valve(fill_tubing_with_port), speed_code)
                self.sp.execute()

        except Exception as e:
            raise OperationError(f"Error in flow_reagent from port: {port}: {str(e)}")

    def priming_or_clean_up(self, port, flow_rate, volume, use_ports=None):
        """
        Fill the tubings from reagents to selector valves with the corresponding reagents. Finally, fill the tubings before 
        syringe pump with {volume} of the reagent from {port}.
        This method should work for both priming and cleaning. For priming, use a wash buffer for {port}; for cleaning, use water
        for all ports.
        """
        speed_code = self.sp.flow_rate_to_speed_code(flow_rate)
        try:
            self.sp.reset_chain()
            for i in range(1, self.sv.available_port_number + 1):
                if use_ports is not None and i not in use_ports:
                    continue
                volume_to_port = self.sv.get_tubing_fluid_amount_to_port(i)
                if i != port and volume_to_port:
                    self._empty_syringe_pump_on_full(volume_to_port)
                    self.sv.open_port(i)
                    self.sp.extract(self.extract_port, volume_to_port, speed_code)
                    self.sp.execute()
                    if self.sp.is_aborted:
                        return

            self.sv.open_port(port)
            self._empty_syringe_pump_on_full(volume)
            self.sp.extract(self.extract_port, volume, speed_code)
            self.sp.execute()
        except Exception as e:
            raise OperationError(f"Error in priming_or_clean_up: {str(e)}")
