from control._def import CMD_SET

class SelectorValve():
    def __init__(self, fluid_controller, config, valve_id, initial_pos=1):
        self.fc = fluid_controller
        self.id = valve_id
        self.position = initial_pos
        self.config = config

        self.tubing_fluid_amount_ul = self.config['selector_valves']['tubing_fluid_amount_to_valve_ul'][str(valve_id)]
        self.number_of_ports = self.config['selector_valves']['number_of_ports'][str(valve_id)]
        self.fc.send_command(CMD_SET.INITIALIZE_ROTARY, valve_id, self.number_of_ports)
        self.open(self.position)
        print(f"Selector valve id = {valve_id} initialized.")

    def open(self, port):
        print("open", self.id, port)
        self.fc.send_command(CMD_SET.SET_ROTARY_VALVE, self.id, port)
        self.position = port


class SelectorValveSystem():
    PORTS_PER_VALVE = 10

    def __init__(self, fluid_controller, config):
        self.fc = fluid_controller
        self.config = config
        self.valves = [None] * len(self.config['selector_valves']['valve_ids_allowed'])
        sv = self.config['selector_valves']['valve_ids_allowed']
        self.available_port_number = 0
        for i, valve_id in enumerate(sv[:-1]):
            ports = self.config['selector_valves']['number_of_ports'][str(valve_id)]
            self.valves[i] = SelectorValve(self.fc, self.config, i, ports)
            self.available_port_number += (ports - 1)
        self.valves[-1] = SelectorValve(self.fc, self.config, sv[-1], 1)
        self.current_port = self.available_port_number + 1
        self.available_port_number += self.config['selector_valves']['number_of_ports'][str(sv[-1])]

    def port_to_reagent(self, port_index):
        if port_index > self.available_port_number:
            return None
        else:
            return self.config['selector_valves']['reagent_name_mapping']['port_' + str(port_index)]

    def open_port(self, port_index):
        if port_index > self.available_port_number:
            return
            
        ports_processed = 0
        for valve in self.valves[:-1]:  # Process all valves except the last one
            ports_in_valve = valve.number_of_ports - 1
            if port_index > (ports_processed + ports_in_valve):
                valve.open(ports_in_valve + 1)  # Open the last port
                self.fc.wait_for_completion()
                ports_processed += ports_in_valve
            else:
                valve.open(port_index - ports_processed)
                self.fc.wait_for_completion()
                self.current_port = port_index
                return

        # If we get here, it's in the last valve
        self.valves[-1].open(port_index - ports_processed)
        self.fc.wait_for_completion()
        self.current_port = port_index
        return

    def get_tubing_fluid_amount_to_valve(self, port_index):
        # Return the tubing fluid amount from selector valve to sample. Used for fill_tubing_with.
        ports_processed = 0
        for i, valve in enumerate(self.valves[:-1]):
            ports_in_valve = valve.number_of_ports - 1  # Subtract 1 because last port is for passing through
            if port_index > (ports_processed + ports_in_valve):
                ports_processed += ports_in_valve
            else:
                return valve.tubing_fluid_amount_ul

        # If we get here, it's in the last valve
        return self.valves[-1].tubing_fluid_amount_ul

    def get_tubing_fluid_amount_to_port(self, port_index):
        # Return the tubing fluid amount from reagent to selector valve port. Used for priming and cleaning up.
        return self.config['selector_valves']['tubing_fluid_amount_to_port_ul']['port_' + str(port_index)]

    def get_port_names(self):
        names = []
        for i in range(1, self.available_port_number + 1):
            names.append('Port ' + str(i) + ': ' + self.config['selector_valves']['reagent_name_mapping']['port_' + str(i)])
        return names

    def get_current_port(self):
        return self.current_port