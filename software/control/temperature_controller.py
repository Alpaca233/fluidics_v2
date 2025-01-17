import serial
from serial.tools import list_ports

import threading
import time

from zlib import crc32

class TCMController():
    def __init__(self, sn, baud_rate=57600, timeout=0.5):
        port = [p.device for p in list_ports.comports() if sn == p.serial_number]

        if not port:
            raise ValueError(f"No device found with serial number: {sn}")

        self.serial = serial.Serial(port[0], baudrate=baud_rate, timeout=timeout)
        self.serial_lock = threading.Lock()

        self.target_temperature_ch1 = self.get_target_temperature('TC1')
        self.target_temperature_ch2 = self.get_target_temperature('TC2')
        
        self.t1 = 0
        self.t2 = 0

        self.temperature_updating_callback = None
        self.actual_temp_updating_thread = threading.Thread(target=self.update_temperature, daemon=True)
        self.terminate_temperature_updating_thread = False

    def send_command(self, command, module):
        with self.serial_lock:
            self.serial.write(f"{module}:{command}\r".encode())
            response = self.serial.readline().decode().strip()
            if response[:4] == 'CMD:' and response[-1] != '1' and response[-1] != '8':
                raise Exception(f"Error from controller: {response}")
            return response

    def get_target_temperature(self, channel):
        response = self.send_command('TCADJTEMP?', channel)
        temp = float(response[14:])
        if channel == 'TC1':
            self.target_temperature_ch1 = temp
        else:
            self.target_temperature_ch2 = temp
        return temp

    def set_target_temperature(self, channel, t):
        self.send_command('TCADJTEMP=' + str(t), channel)
        if channel == 'TC1':
            self.target_temperature_ch1 = t
        else:
            self.target_temperature_ch2 = t

    def save_target_temperature(self, channel):
        response = self.send_command('TCADJTEMP!', channel)
        print('Save target temperature: ', response)

    def get_actual_temperature(self, channel):
        response = self.send_command('TCACTUALTEMP?', channel)
        try:
            temp = float(response[17:])
        except:
            # Handle empty responses
            if channel == 'TC1':
                temp = self.t1
            else:
                temp = self.t2
        return temp

    def update_temperature(self):
        while self.terminate_temperature_updating_thread == False:
            time.sleep(1)
            self.t1 = self.get_actual_temperature('TC1')
            self.t2 = self.get_actual_temperature('TC2')
            if self.temperature_updating_callback is not None:
                try:
                    self.temperature_updating_callback(self.t1, self.t2)
                except TypeError as ex:
                    print("Temperature read callback failed")

class TCMControllerSimulation():
    def __init__(self, sn, baud_rate=57600, timeout=0.5):
        self.target_temperature_ch1 = self.get_target_temperature('TC1')
        self.target_temperature_ch2 = self.get_target_temperature('TC2')

        self.temperature_updating_callback = None
        self.actual_temp_updating_thread = threading.Thread(target=self.update_temperature, daemon=True)
        self.terminate_temperature_updating_thread = False

    def send_command(self, command, module, type):
        pass

    def get_target_temperature(self, channel):
        return 10.0

    def set_target_temperature(self, channel, t):
        pass

    def save_target_temperature(self, channel):
        pass

    def get_actual_temperature(self, channel):
        return 12.0

    def update_temperature(self):
        while self.terminate_temperature_updating_thread == False:
            time.sleep(1)
            t1 = self.get_actual_temperature('TC1')
            t2 = self.get_actual_temperature('TC2')
            if self.temperature_updating_callback is not None:
                try:
                    self.temperature_updating_callback(t1, t2)
                except TypeError as ex:
                    print("Temperature read callback failed")
