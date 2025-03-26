from ._def import CMD_SET, MCU_CONSTANTS
import time

class DiscPump():
    def __init__(self, fluid_controller):
        self.fc = fluid_controller
        self.fc.send_command(CMD_SET.INITIALIZE_DISC_PUMP, MCU_CONSTANTS.TTP_MAX_PW)
        print('Disc pump initiated.')

    def aspirate(self, time_s):
        self.fc.send_command(CMD_SET.SET_PUMP_PWR_OPEN_LOOP, MCU_CONSTANTS.TTP_MAX_PW)
        time.sleep(time_s)
        self.fc.send_command(CMD_SET.SET_PUMP_PWR_OPEN_LOOP, 0)
        self.fc.wait_for_completion()

    def start(self, power_percentage):
        self.fc.send_command(CMD_SET.SET_PUMP_PWR_OPEN_LOOP, power_percentage * MCU_CONSTANTS.TTP_MAX_PW)
        self.fc.wait_for_completion()

    def stop(self):
        self.fc.send_command(CMD_SET.SET_PUMP_PWR_OPEN_LOOP, 0)
        self.fc.wait_for_completion()