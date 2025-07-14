from time import sleep, time
from .experiment_worker import AbortRequested, OperationError

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

        if sequence_name.startswith("Add Reagent"):
            self.add_reagent(port, flow_rate, volume, fill_tubing_with)
        elif sequence_name.startswith("Clear Tubings and Add Reagent"):
            self.clear_and_add_reagent(port, flow_rate, volume, fill_tubing_with)
        elif sequence_name == "Wash with Constant Flow":
            self.wash_with_constant_flow(port, flow_rate, volume, fill_tubing_with)
        elif sequence_name == "Priming":
            self.priming_or_clean_up(port, flow_rate, volume)
        elif sequence_name == "Clean Up":
            self.priming_or_clean_up(port, flow_rate, volume, clean_up=True)
        elif sequence_name.startswith("Set Temperature"):
            self.set_temperature(float(sequence_name.split()[-1]))
        else:
            raise ValueError(f"Unknown sequence name: {sequence_name}")

    def _empty_syringe_pump_on_full(self, volume):
        if self.sp.get_current_volume() + self.sp.get_chained_volume() + volume > 0.95 * self.config['syringe_pump']['volume_ul']:
            try:
                self.sp.dispense_to_waste()
                self.sp.execute()
            except Exception as e:
                raise OperationError(f"Failed to empty syringe pump: {str(e)}")

    def clear_and_add_reagent(self, port, flow_rate, volume, fill_tubing_with_port):
        """
        Clear previous liquid in tubings by 1) dispensing sv_to_sp into waste and 2) dispensing sp_to_oc into sample and aspirate,
        then add reagent from {port}
        """
        speed_code = self.sp.flow_rate_to_speed_code(flow_rate)
        volume = min(self.config['chamber_volume_ul'], volume)
        try:
            self.sp.reset_chain()
            self.sp.dispense_to_waste(self.config['syringe_pump']['speed_code_limit'])
            if self.sp.is_aborted:
                return
            self.sp.execute()
            if self.sp.is_aborted:
                return
            self.sv.open_port(port)
            # Clear previous buffer in tubings (selector valve to syringe pump)
            self.sp.extract(self.config['syringe_pump']['extract_port'], self.config['tubing_fluid_amount_sv_to_sp_ul'], self.config['syringe_pump']['speed_code_limit'])
            self.sp.dispense_to_waste(self.config['syringe_pump']['speed_code_limit'])
            # Assume reagent volume is greater than 'tubing_fluid_amount_sv_to_sp_ul'
            self.sp.extract(self.config['syringe_pump']['extract_port'], volume - self.config['tubing_fluid_amount_sv_to_sp_ul'], self.config['syringe_pump']['speed_code_limit'])
            if self.sp.is_aborted:
                return
            self.sp.execute()
            if self.sp.is_aborted:
                return
            if fill_tubing_with_port:
                self.sv.open_port(int(fill_tubing_with_port))
            # Draw all reagent into syringe
            self.sp.extract(self.config['syringe_pump']['extract_port'], self.config['tubing_fluid_amount_sv_to_sp_ul'], self.config['syringe_pump']['speed_code_limit'])
            if self.sp.is_aborted:
                return
            self.sp.execute()
            if self.sp.is_aborted:
                return
            self.dp.aspirate(10)
            # Clear previous buffer in tubings (syringe pump to chamber)
            # Assume reagent volume is greater than 'tubing_fluid_amount_sp_to_oc_ul'
            self.sp.dispense(self.config['syringe_pump']['dispense_port'], self.config['tubing_fluid_amount_sp_to_oc_ul'], speed_code)
            if self.sp.is_aborted:
                return
            self.sp.execute()
            if self.sp.is_aborted:
                return
            self.dp.aspirate(10)
            # Push reagent to open chamber
            self.sp.dispense(self.config['syringe_pump']['dispense_port'], volume - self.config['tubing_fluid_amount_sp_to_oc_ul'], speed_code)
            self.sp.extract(self.config['syringe_pump']['extract_port'], self.config['tubing_fluid_amount_sp_to_oc_ul'], self.config['syringe_pump']['speed_code_limit'])
            self.sp.dispense(self.config['syringe_pump']['dispense_port'], self.config['tubing_fluid_amount_sp_to_oc_ul'], speed_code)
            if self.sp.is_aborted:
                return
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
            self.sp.dispense_to_waste(self.config['syringe_pump']['speed_code_limit'])
            if self.sp.is_aborted:
                return
            self.sp.execute()
            if self.sp.is_aborted:
                return
            # Assume syringe_volume > (sp_to_oc + sv_to_sp) > sp_to_oc > sv_to_sp > overflow (sp_to_oc + sv_to_sp - chamber_volume)
            # and syringe_volume > chamber_volume > sp_to_oc > sv_to_sp > overflow (sp_to_oc + sv_to_sp - chamber_volume)
            # TODO: Make sure if this assumption is true in most cases. If not, we may need to update the sequence logic
            syringe_vol = 0
            if fill_tubing_with_port:
                self.sv.open_port(port)
                syringe_vol += max(volume - self.config['tubing_fluid_amount_sp_to_oc_ul'] - self.config['tubing_fluid_amount_sv_to_sp_ul'], 0)
                self.sp.extract(self.config['syringe_pump']['extract_port'], syringe_vol, self.config['syringe_pump']['speed_code_limit'])
                if self.sp.is_aborted:
                    return
                self.sp.execute()
                if self.sp.is_aborted:
                    return
                self.sv.open_port(int(fill_tubing_with_port))
                # Draw sv_to_sp into syringe
                syringe_vol += self.config['tubing_fluid_amount_sv_to_sp_ul']
                self.sp.extract(self.config['syringe_pump']['extract_port'], self.config['tubing_fluid_amount_sv_to_sp_ul'], self.config['syringe_pump']['speed_code_limit'])
                # Discard overflow amount (in the case chamber_volume < sp_to_oc + sv_to_sp)
                overflow = max(self.config['tubing_fluid_amount_sp_to_oc_ul'] + self.config['tubing_fluid_amount_sv_to_sp_ul'] - volume, 0)
                syringe_vol -= overflow
                if overflow > 0:
                    self.sp.dispense(self.config['syringe_pump']['waste_port'], overflow, speed_code)
                    if self.sp.is_aborted:
                        return
                    self.sp.execute()
                    if self.sp.is_aborted:
                        return
            else:
                self.sv.open_port(port)
                # Draw the amount needed into syringe (volume - sp_to_oc)
                syringe_vol = volume - self.config['tubing_fluid_amount_sp_to_oc_ul']
                self.sp.extract(self.config['syringe_pump']['extract_port'], syringe_vol, self.config['syringe_pump']['speed_code_limit'])
                if self.sp.is_aborted:
                    return
                self.sp.execute()
                if self.sp.is_aborted:
                    return
            # Push reagent to sample
            self.sp.dispense(self.config['syringe_pump']['dispense_port'], syringe_vol, speed_code)
            self.sp.extract(self.config['syringe_pump']['extract_port'], self.config['tubing_fluid_amount_sp_to_oc_ul'], self.config['syringe_pump']['speed_code_limit'])
            self.sp.dispense(self.config['syringe_pump']['dispense_port'], self.config['tubing_fluid_amount_sp_to_oc_ul'], speed_code)
            # Clear previous liquid in open chamber
            if self.sp.is_aborted:
                return
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
            self.sp.dispense_to_waste(self.config['syringe_pump']['speed_code_limit'])
            if self.sp.is_aborted:
                return
            self.sp.execute()
            if self.sp.is_aborted:
                return
            self.sv.open_port(port)
            # No need to clear previous liquid in tubings (sv_to_sp)
            self.sp.extract(self.config['syringe_pump']['extract_port'], volume - self.config['tubing_fluid_amount_sv_to_sp_ul'], self.config['syringe_pump']['speed_code_limit'])
            if self.sp.is_aborted:
                return
            self.sp.execute()
            if self.sp.is_aborted:
                return
            if fill_tubing_with_port:
                self.sv.open_port(fill_tubing_with_port)
            self.sp.extract(self.config['syringe_pump']['extract_port'], self.config['tubing_fluid_amount_sv_to_sp_ul'], self.config['syringe_pump']['speed_code_limit'])
            self.sp.dispense(self.config['syringe_pump']['dispense_port'], volume, speed_code)
            # Push reagent to open chamber
            if self.sp.is_aborted:
                return
            self.dp.start(0.3)
            self.sp.execute()
            self.dp.stop()
            if fill_tubing_with_port:
                # Wash with additional amount of buffer in tubing sp_to_oc and fill with next reagent
                self.sp.extract(self.config['syringe_pump']['extract_port'], self.config['tubing_fluid_amount_sp_to_oc_ul'], self.config['syringe_pump']['speed_code_limit'])
                self.sp.dispense(self.config['syringe_pump']['dispense_port'], self.config['tubing_fluid_amount_sp_to_oc_ul'], speed_code)
                if self.sp.is_aborted:
                    return
                self.dp.start(0.3)
                self.sp.execute()
                self.dp.stop()
            sleep(1)
        except Exception as e:
            raise OperationError(f"Error in wash_with_constant_flow from port: {port}: {str(e)}")

    def priming_or_clean_up(self, port, flow_rate, volume, use_ports=None, clean_up=False):
        """
        Fill the tubings from reagents to selector valves with the corresponding reagents. Finally, fill the tubings before 
        syringe pump with {volume} of the reagent from {port}.
        This method should work for both priming and cleaning. For priming, use a wash buffer for {port}; for cleaning, use water
        for all ports.
        """
        speed_code = self.sp.flow_rate_to_speed_code(flow_rate)
        # We need to limit the flow rate for priming, because it takes time for flow to stabilize when there's air in the tubings.
        priming_speed_code_limit = self.sp.flow_rate_to_speed_code(8000)
        try:
            self.sp.reset_chain()
            self.sp.dispense_to_waste()
            if self.sp.is_aborted:
                return
            self.sp.execute()  # TODO: needs some refactoring here
            if self.sp.is_aborted:
                return
            for i in range(1, self.sv.available_port_number + 1):
                if use_ports is not None and i not in use_ports:
                    continue
                volume_to_port = self.sv.get_tubing_fluid_amount_to_port(i)
                if volume_to_port:
                    self.sv.open_port(i)
                    self.sp.extract(self.config['syringe_pump']['extract_port'], volume_to_port, priming_speed_code_limit)
                    self.sp.dispense_to_waste()
                    if self.sp.is_aborted:
                        return
                    self.sp.execute()
                    if self.sp.is_aborted:
                        return

            self.sv.open_port(port)
            self.sp.extract(self.config['syringe_pump']['extract_port'], volume, priming_speed_code_limit)
            self.sp.dispense(self.config['syringe_pump']['dispense_port'], volume, speed_code)
            if self.sp.is_aborted:
                return
            self.sp.execute()
            if clean_up:
                self.dp.aspirate(20)
        except Exception as e:
            raise OperationError(f"Error in priming_or_clean_up: {str(e)}")

    # temporary temperature control sequences for testing, using Yexian M207
    def set_temperature(self, target, timeout=300):
        if self.tc:
            self.tc.set_target_temperature('TC1', target)
            self.tc.set_target_temperature('TC2', target)
            start_time = time()
            while True:
                sleep(2)
                if abs(self.tc.t1 - target) <= 1 and abs(self.tc.t2 - target) <= 1:
                    break
                if self.tc.is_aborted:
                    break
                if time() - start_time > timeout:
                    print(f"Temperature failed to stabilize within {timeout} seconds, t1={self.tc.t1}, t2={self.tc.t2}")
                    break
        else:
            print("No temperature controller found. Skipping temperature control sequence.")