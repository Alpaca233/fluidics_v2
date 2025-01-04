from time import sleep
from experiment_worker import AbortRequested, OperationError

class MERFISHOperations():
    def __init__(self, config, syringe_pump, selector_valves):
        self.config = config
        self.sp = syringe_pump
        self.sv = selector_valves
        super().__init__(self.config, self.sp, self.sv)

    def process_sequence(self, sequence):
        print(sequence)
        try:
            sequence_name = sequence['sequence_name']
            port = int(sequence['fluidic_port'])
            flow_rate = int(sequence['flow_rate'])
            volume = int(sequence['volume'])
            incubation_time = int(sequence['incubation_time'])
            fill_tubing_with = sequence['fill_tubing_with']
        except:
            raise ValueError("Invalid sequence")

        if sequence_name == "Flow Bleaching Buffer":
            self.flow_bleaching_buffer(port, flow_rate, volume, incubation_time, fill_tubing_with)
        elif sequence_name == "Hybridize":
            self.hybridize(port, flow_rate, volume, incubation_time, fill_tubing_with)
        elif sequence_name == "Flow Wash Buffer":
            self.flow_wash_buffer(port, flow_rate, volume, incubation_time, fill_tubing_with)
        elif sequence_name == "Flow Imaging Buffer":
            self.flow_imaging_buffer(port, flow_rate, volume, incubation_time, fill_tubing_with)
        elif sequence_name == "Clean Up":
            self.clean_up(port, flow_rate, volume)
        else:
            raise ValueError(f"Unknown sequence name: {sequence_name}")

    def flow_bleaching_buffer(self, port, flow_rate, volume, incubation_time, fill_tubing_with_port):
        speed_code = self.sp.flow_rate_to_speed_code(flow_rate)
        try:
            self.sv.open_port(port)
            self.sp.reset_chain()
            self.sp.extract(2, volume, speed_code)
            self.sp.execute()
            if fill_tubing_with_port:
                self.sv.open_port(int(fill_tubing_with_port))
                self.sp.extract(2, self.sv.get_tubing_fluid_amount(fill_tubing_with_port), speed_code)
                self.sp.execute()
        except:
            raise OperationError(f"Error in Flow Bleaching Buffer: {str(e)}")

    def hybridize(self, port, flow_rate, volume, incubation_time, fill_tubing_with_port):
        speed_code = self.sp.flow_rate_to_speed_code(flow_rate)
        try:
            self.sp.reset_chain()
            self.sp.dispense_to_waste(10)
            self.sp.execute()
            self.sv.open_port(port)
            self.sp.extract(2, volume, speed_code)
            self.sp.execute()
            if fill_tubing_with_port:
                self.sv.open_port(int(fill_tubing_with_port))
                self.sp.extract(2, self.sv.get_tubing_fluid_amount(fill_tubing_with_port), speed_code)
                self.sp.execute()
        except:
            raise OperationError(f"Error in Hybridize: {str(e)}")

    def flow_wash_buffer(self, port, flow_rate, volume, incubation_time, fill_tubing_with_port):
        speed_code = self.sp.flow_rate_to_speed_code(flow_rate)
        try:
            self.sp.reset_chain()
            self.sp.dispense_to_waste(10)
            self.sp.execute()
            self.sv.open_port(port)
            self.sp.extract(2, volume, speed_code)
            self.sp.execute()
            self.incubate(incubation_time, "Wash Buffer")
            if fill_tubing_with_port:
                self.sv.open_port(int(fill_tubing_with_port))
                self.sp.extract(2, self.sv.get_tubing_fluid_amount(fill_tubing_with_port), speed_code)
                self.sp.execute()

        except:
            raise OperationError(f"Error in Flow Wash Buffer: {str(e)}")

    def flow_imaging_buffer(self, port, flow_rate, volume, incubation_time, fill_tubing_with_port):
        speed_code = self.sp.flow_rate_to_speed_code(flow_rate)
        try:
            self.sp.reset_chain()
            self.sp.dispense_to_waste(10)
            self.sp.execute()
            self.sv.open_port(port)
            self.sp.extract(2, volume, speed_code)
            self.sp.execute()
            self.incubate(incubation_time, "Imaging Buffer")
            if fill_tubing_with_port:
                self.sv.open_port(int(fill_tubing_with_port))
                self.sp.extract(2, self.sv.get_tubing_fluid_amount(fill_tubing_with_port), speed_code)
                self.sp.execute()
        except:
            raise OperationError(f"Error in Flow Imaging Buffer: {str(e)}")

    def clean_up(self, port, flow_rate, volume):
        speed_code = self.sp.flow_rate_to_speed_code(flow_rate)
        try:
            self.sp.reset_chain()
            self.sp.dispense_to_waste(10)
            self.sp.execute()
            self.sv.open_port(port)
            self.sp.extract(2, volume, speed_code)
            self.sp.execute()
        except:
            raise OperationError(f"Error in Flow Imaging Buffer: {str(e)}")
