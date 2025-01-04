from controller import FluidControllerSimulation as FluidController
from _def import CMD_SET

class SelectorValve():
    def __init__(self, fluid_controller, config, valve_id, initial_pos=1):
        self.fc = fluid_controller
        self.id = valve_id
        self.position = initial_pos
        self.fc.send_command(CMD_SET.INITIALIZE_ROTARY, valve_id, SelectorValveSystem.PORTS_PER_VALVE)
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
        sv = sorted(self.config['selector_valves']['valve_ids_allowed'])
        for i in sv[:-1]:
            self.valves[i] = SelectorValve(self.fc, self.config, i, self.PORTS_PER_VALVE)
        self.valves[sv[-1]] = SelectorValve(self.fc, self.config, sv[-1], 1)
        self.available_port_number = (self.PORTS_PER_VALVE - 1) * len(self.valves) + 1

    def port_to_reagent(self, port_index):
        if port_index > self.available_port_number:
            return None
        else:
            return self.config['selector_valves']['reagent_name_mapping']['port_' + str(port_index)]

    def open_port(self, port_index):
        target_valve = ((port_index - 1) // (self.PORTS_PER_VALVE - 1))
        if target_valve == len(self.valves):
            target_port = self.PORTS_PER_VALVE
            target_valve -= 1
        else:
            target_port = (port_index - 1) % (self.PORTS_PER_VALVE - 1) + 1

        self.valves[target_valve].open(target_port)
        self.fc.wait_for_completion()

        for i in range(target_valve):
            self.valves[i].open(10)
            self.fc.wait_for_completion()

    def get_tubing_fluid_amount(self, port_index):
        '''
        target_valve = ((port_index - 1) // (self.PORTS_PER_VALVE - 1))
        if target_valve == len(self.valves):
            target_valve -= 1

        total_amount = 0 	# ul
        for i in range(target_valve + 1):
            total_amount += self.valves[i].tubing_fluid_amount
        '''
        return self.config['selector_valves']['tubing_fluid_amount_ul']

    def get_port_names(self):
        names = []
        for i in range(1, self.available_port_number + 1):
            names.append('Port ' + str(i) + ': ' + self.config['selector_valves']['reagent_name_mapping']['port_' + str(i)])
        return names
