from time import sleep, time
from experiment_worker import AbortRequested, OperationError

class OpenChamberOperations():
    def __init__(self, config, syringe_pump, selector_valves, disc_pump, temperature_controller=None):
        self.config = config
        self.sp = syringe_pump
        self.sv = selector_valves
        self.dp = disc_pump
        self.tc = temperature_controller

    def process_sequence(self, sequence):
        # TODO: In open chamber sequences, use a 'time' or 'power' field for operating disc pump. Planning to do this after moving to YAML
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

        if sequence_name == "Add Reagent":
            self.add_reagent(port, flow_rate, volume, fill_tubing_with)
        elif sequence_name == "Clear Tubings and Add Reagent":
            self.clear_and_add_reagent(port, flow_rate, volume, fill_tubing_with)
        elif sequence_name == "Wash with Constant Flow":
            self.wash_with_constant_flow(port, flow_rate, volume, fill_tubing_with)
        elif sequence_name in ("Priming", "Clean Up"):
            self.priming_or_clean_up(port, flow_rate, volume)
        elif sequence_name.startswith("Set Temperature"):
            self.set_temperature(float(sequence_name.split()[-1]))
        else:
            raise ValueError(f"Unknown sequence name: {sequence_name}")

    def clear_and_add_reagent(self, port, flow_rate, volume, fill_tubing_with_port):
        """
        Clear previous liquid in tubings by 1) dispensing sv_to_sp into waste and 2) dispensing sp_to_oc into sample and aspirate,
        then add reagent from {port}
        """
        speed_code = self.sp.flow_rate_to_speed_code(flow_rate)
        volume = min(self.config['chamber_volume_ul'], volume)
        try:
            self.sp.reset_chain()
            self.sv.open_port(port)
            # Clear previous buffer in tubings (selector valve to syringe pump)
            self.sp.extract(self.config['syringe_pump']['extract_port'], self.config['tubing_fluid_amount_sv_to_sp_ul'], self.config['syringe_pump']['speed_code_limit'])
            self.sp.dispense_to_waste(self.config['syringe_pump']['speed_code_limit'])
            # Assume reagent volume is greater than 'tubing_fluid_amount_sv_to_sp_ul'
            self.sp.extract(self.config['syringe_pump']['extract_port'], volume - self.config['tubing_fluid_amount_sv_to_sp_ul'], self.config['syringe_pump']['speed_code_limit'])
            self.sp.execute()
            if fill_tubing_with_port:
                self.sv.open_port(int(fill_tubing_with_port))
            # Clear previous buffer in tubings (syringe pump to chamber)
            self.sp.extract(self.config['syringe_pump']['extract_port'], self.config['tubing_fluid_amount_sv_to_sp_ul'], self.config['syringe_pump']['speed_code_limit'])
            self.sp.execute()
            self.dp.aspirate(10)
            # Assume reagent volume is greater than 'tubing_fluid_amount_sp_to_oc_ul'
            self.sp.dispense(self.config['syringe_pump']['dispense_port'], self.config['tubing_fluid_amount_sp_to_oc_ul'], speed_code)
            self.sp.execute()
            self.dp.aspirate(10)
            # Push reagent to open chamber
            self.sp.dispense(self.config['syringe_pump']['dispense_port'], volume - self.config['tubing_fluid_amount_sp_to_oc_ul'], speed_code)
            self.sp.extract(self.config['syringe_pump']['extract_port'], self.config['tubing_fluid_amount_sp_to_oc_ul'], self.config['syringe_pump']['speed_code_limit'])
            self.sp.dispense(self.config['syringe_pump']['dispense_port'], self.config['tubing_fluid_amount_sp_to_oc_ul'], speed_code)
            self.sp.execute()
        except Exception as e:
            raise OperationError(f"Error in clear_and_add_reagent from port: {port}: {str(e)}")

    def add_reagent(self, port, flow_rate, volume, fill_tubing_with_port):
        """
        Add the reagent from {port} to the chamber, assuming tubings already contain the same reagent.
        """
        speed_code = self.sp.flow_rate_to_speed_code(flow_rate)
        volume = min(self.config['chamber_volume_ul'], volume)
        try:
            self.sp.reset_chain()
            # Assume syringe_volume > (sp_to_oc + sv_to_sp) > chamber_volume > sp_to_oc > sv_to_sp > overflow (sp_to_oc + sv_to_sp - chamber_volume)
            # TODO: Make sure if this assumption is true in most cases. If not, we may need to update the sequence logic
            if fill_tubing_with_port:
                self.sv.open_port(int(fill_tubing_with_port))
                # Draw sv_to_sp into syringe
                self.sp.extract(self.config['syringe_pump']['extract_port'], self.config['tubing_fluid_amount_sv_to_sp_ul'], self.config['syringe_pump']['speed_code_limit'])
                # Discard overflow amount
                overflow = self.config['tubing_fluid_amount_sp_to_oc_ul'] + self.config['tubing_fluid_amount_sv_to_sp_ul'] - volume
                self.sp.dispense(self.config['syringe_pump']['dispense_port'], overflow, speed_code)
                self.dp.aspirate(10)
                self.sp.execute()
            else:
                self.sv.open_port(port)
                # Draw the amount needed into syringe (volume - sp_to_oc)
                self.sp.extract(self.config['syringe_pump']['extract_port'], volume - self.config['tubing_fluid_amount_sp_to_oc_ul'], self.config['syringe_pump']['speed_code_limit'])
                self.dp.aspirate(10)
                self.sp.execute()
            # Push reagent to sample
            self.sp.dispense(self.config['syringe_pump']['dispense_port'], volume - self.config['tubing_fluid_amount_sp_to_oc_ul'], speed_code)
            self.sp.extract(self.config['syringe_pump']['extract_port'], self.config['tubing_fluid_amount_sp_to_oc_ul'], self.config['syringe_pump']['speed_code_limit'])
            self.sp.dispense(self.config['syringe_pump']['dispense_port'], self.config['tubing_fluid_amount_sp_to_oc_ul'], speed_code)
            self.dp.aspirate(10)
            self.sp.execute()
        except Exception as e:
            raise OperationError(f"Error in add_reagent from port: {port}: {str(e)}")

    def wash_with_constant_flow(self, port, flow_rate, volume, fill_tubing_with_port):
        """
        Add reagent from {port} while draining with disc pump on the othe side to keep a constant flow in the chamber.
        """
        speed_code = self.sp.flow_rate_to_speed_code(flow_rate)
        volume = min(self.config['syringe_pump']['volume_ul'], volume)
        try:
            self.sp.reset_chain()
            self.sv.open_port(port)
            # No need to clear previous liquid in tubings (sv_to_sp)
            self.sp.extract(self.config['syringe_pump']['extract_port'], volume - self.config['tubing_fluid_amount_sv_to_sp_ul'], self.config['syringe_pump']['speed_code_limit'])
            self.sp.execute()
            if fill_tubing_with_port:
                self.sv.open_port(fill_tubing_with_port)
            self.sp.extract(self.config['syringe_pump']['extract_port'], self.config['tubing_fluid_amount_sv_to_sp_ul'], self.config['syringe_pump']['speed_code_limit'])
            self.sp.dispense(self.config['syringe_pump']['dispense_port'], volume, speed_code)
            # Push reagent to open chamber
            self.dp.start(0.3)
            self.sp.execute()
            self.dp.stop()
            if fill_tubing_with_port:
                # Wash with additional amount of buffer in tubing sp_to_oc and fill with next reagent
                self.sp.extract(self.config['syringe_pump']['extract_port'], self.config['tubing_fluid_amount_sp_to_oc_ul'], self.config['syringe_pump']['speed_code_limit'])
                self.sp.dispense(self.config['syringe_pump']['dispense_port'], self.config['tubing_fluid_amount_sp_to_oc_ul'], speed_code)
                self.dp.start(0.3)
                self.sp.execute()
                self.dp.stop()
            sleep(1)
        except Exception as e:
            raise OperationError(f"Error in wash_with_constant_flow from port: {port}: {str(e)}")

    def priming_or_clean_up(self, port, flow_rate, volume):
        raise OperationError("priming_or_clean_up not implemented")

    # temporary temperature control sequences for testing, using Yexian M207
    def set_temperature(self, target, timeout=300):
        if self.tc:
            self.tc.set_target_temperature('TC1', target)
            self.tc.set_target_temperature('TC2', target)
            start_time = time()
            while True:
                if abs(self.tc.t1 - target) <= 1 and abs(self.tc.t1 - target):
                    break
                if time() - start_time > timeout:
                    raise TimeoutError(f"Temperature failed to stabilize within {timeout} seconds")

            sleep(2)
