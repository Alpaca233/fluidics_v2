import fluidics.control.tecancavro as tecancavro
import time
from serial.tools import list_ports

class SyringePump:
    SPEED_SEC_MAPPING = [1.25, 1.30, 1.39, 1.52, 1.71, 1.97, 2.37, 2.77, 3.03, 3.36, 3.77, 
                        4.30, 5.00, 6.00, 7.50, 10.00, 15.00, 30.00, 31.58, 33.33, 35.29,
                        37.50, 40.00, 42.86, 46.15, 50.00, 54.55, 60.00, 66.67, 75.00, 85.71,
                        100.00, 120.00, 150.00, 200.00, 300.00, 333.33, 375.00, 428.57, 500.00, 600.00]
                        # Maps to speed code 0-40

    def __init__(self, sn, syringe_ul, speed_code_limit, waste_port, num_ports=4, slope=14, debug=False):
        if sn is not None:
            for d in list_ports.comports():
                if d.serial_number == sn:
                    self.port = d.device
                    self.com_link = tecancavro.TecanAPISerial(tecan_addr=0, ser_port=self.port, ser_baud=9600)
                    print("Syringe pump found.")
                    break
        self.syringe = tecancavro.models.XCaliburD(com_link=self.com_link,
                            num_ports=num_ports,
                            syringe_ul=syringe_ul,
                            microstep=False,
                            waste_port=waste_port,
                            slope=slope,
                            debug=debug,
                            debug_log_path='.')
        self.volume = syringe_ul
        self.speed_code_limit = speed_code_limit
        self.range = 3000  # Property of the syringe pump
        self.chained_volume = 0

        self.get_plunger_position()

        self.is_busy = False
        self.is_aborted = False

        print("Syringe pump initialized.")

    def get_plunger_position(self):
        position = self.syringe.getPlungerPos()
        self.plunger_pos = position / self.range
        return self.plunger_pos

    def get_current_volume(self):
        return self.volume * self.plunger_pos  # ul

    def get_chained_volume(self):
        return self.chained_volume  # ul

    def set_speed(self, speed_code):
        self.syringe.setSpeed(speed_code)

    def set_wait(self, time_s):
        self.syringe.delayExec(time_s * 1000)

    def reset_chain(self):
        self.syringe.resetChain()
        self.chained_volume = 0

    def execute(self, block_pump=False):
        if self.is_aborted:
            return
        self.is_busy = True
        t = self.syringe.executeChain(minimal_reset=True)
        if block_pump:
            self.syringe.waitReady()
            self.is_busy = False
        else:
            self.wait_for_stop(t)
        self.get_plunger_position()
        self.chained_volume = 0

    def get_time_to_finish(self):
        return self.syringe.exec_time

    def dispense(self, port, volume, speed_code):
        if self.is_aborted:
            return
        self.set_speed(max(speed_code, self.speed_code_limit))
        self.syringe.dispense(port, volume)
        self.chained_volume = self.chained_volume - volume
        return self.get_time_to_finish()

    def extract(self, port, volume, speed_code):
        if self.is_aborted:
            return
        self.set_speed(max(speed_code, self.speed_code_limit))
        self.syringe.extract(port, volume)
        self.chained_volume = self.chained_volume + volume
        return self.get_time_to_finish()

    def dispense_to_waste(self, speed_code=None):
        if self.is_aborted:
            return
        if speed_code is None:
            self.set_speed(self.speed_code_limit)
        else:
            self.set_speed(speed_code)
        self.syringe.dispenseToWaste(retain_port=False)
        self.chained_volume = 0
        return self.get_time_to_finish()

    def abort(self):
        self.syringe.terminateCmd()
        self.is_aborted = True

    def reset_abort(self):
        self.is_aborted = False

    def wait_for_stop(self, t=0):
        time.sleep(t)
        while True:
            if self.is_aborted:
                self.is_busy = False
                return
            if self.syringe._checkReady():
                self.is_busy = False
                break
            time.sleep(0.5)

    def get_flow_rate(self, speed_code):
        return round(self.volume * 60 / (self.SPEED_SEC_MAPPING[speed_code] * 1000), 2)

    def flow_rate_to_speed_code(self, target_flow_rate):
        """
        Map any flow rate to the closest speed code of the syringe pump
        
        :param flow_rate: ul/min
        :return: speed code (int)
        """
        # TODO: move this to utils
        target_time = self.volume * 60 / target_flow_rate

        left = 0
        right = len(self.SPEED_SEC_MAPPING) - 1

        # If target is beyond the range, return the closest endpoint
        if target_time <= self.SPEED_SEC_MAPPING[self.speed_code_limit]:
            return self.speed_code_limit
        if target_time >= self.SPEED_SEC_MAPPING[-1]:
            return len(self.SPEED_SEC_MAPPING) - 1

        # Binary search
        while left < right:
            if right - left == 1:
                if abs(self.SPEED_SEC_MAPPING[left] - target_time) <= abs(self.SPEED_SEC_MAPPING[right] - target_time):
                    return left
                return right

            mid = (left + right) // 2
            mid_value = self.SPEED_SEC_MAPPING[mid]

            if mid_value == target_time:
                return mid
            elif mid_value > target_time:
                right = mid
            else:
                left = mid

        return left

    def close(self, to_waste=False):
        if to_waste:
            self.dispense_to_waste(self.speed_code_limit)
            self.execute()
        del self.com_link

class SyringePumpSimulation():
    SPEED_SEC_MAPPING = [1.25, 1.30, 1.39, 1.52, 1.71, 1.97, 2.37, 2.77, 3.03, 3.36, 3.77, 
                        4.30, 5.00, 6.00, 7.50, 10.00, 15.00, 30.00, 31.58, 33.33, 35.29,
                        37.50, 40.00, 42.86, 46.15, 50.00, 54.55, 60.00, 66.67, 75.00, 85.71,
                        100.00, 120.00, 150.00, 200.00, 300.00, 333.33, 375.00, 428.57, 500.00, 600.00]
                        # Maps to speed code 0-40

    def __init__(self, sn, syringe_ul, speed_code_limit, waste_port, num_ports=4, slope=14):
        self.syringe = None
        self.volume = syringe_ul
        self.range = 3000
        self.is_busy = False
        self.is_aborted = False
        self.get_plunger_position()
        print("Simulated syringe pump.")

    def get_plunger_position(self):
        self.plunger_pos = 0.5
        return self.plunger_pos

    def get_current_volume(self):
        return self.volume * self.plunger_pos

    def get_chained_volume(self):
        return 0

    def set_speed(self, speed_code):
        pass

    def set_wait(self, time_s):
        pass

    def reset_chain(self):
        pass

    def execute(self, block_pump=False):
        self.is_busy = True
        self.wait_for_stop(5)

    def get_time_to_finish(self):
        return 5

    def dispense(self, port, volume, speed_code):
        return 5

    def extract(self, port, volume, speed_code):
        return 5

    def dispense_to_waste(self, speed_code):
        return 5

    def abort(self):
        self.is_aborted = True

    def reset_abort(self):
        self.is_aborted = False

    def wait_for_stop(self, t=0):
        time.sleep(t)
        self.is_busy = False
        return

    def get_flow_rate(self, speed_code):
        return round(self.volume * 60 / (self.SPEED_SEC_MAPPING[speed_code] * 1000), 2)

    def flow_rate_to_speed_code(self, target_flow_rate):
        return 20

    def close(self, to_waste=False):
        pass
