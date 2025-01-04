from controller import FluidController
from _def import CMD_SET, MCU_CONSTANTS, COMMAND_STATUS, VALVE_POSITIONS
from controller import SERIAL_NUMBER_DEBUGGING

PRESSURE_TEST = 5.0
VACUUM_TEST = -2.0
DO_PRESSURE_VACUUM_TEST = False
CTRL = "bb/flow" # 'bb', "open", "press_pid", "bb/flow"

fc = FluidController(SERIAL_NUMBER_DEBUGGING, log_measurements=True, debug=False)

def initialize_device(fc):
    fc.begin()
    fc.send_command_blocking(CMD_SET.CLEAR)
    fc.send_command_blocking(CMD_SET.INITIALIZE_PRESSURE_SENSOR, 0)
    fc.send_command_blocking(CMD_SET.INITIALIZE_PRESSURE_SENSOR, 1)
    fc.send_command_blocking(CMD_SET.INITIALIZE_FLOW_SENSOR, 1, MCU_CONSTANTS.SLF3X_WATER, True)
    fc.send_command_blocking(CMD_SET.INITIALIZE_VALVES)
    fc.send_command_blocking(CMD_SET.INITIALIZE_ROTARY, 0, 10)
    fc.send_command_blocking(CMD_SET.INITIALIZE_ROTARY, 1, 10)

    # Take 2 tries to init the disc pump
    result = fc.send_command_blocking(CMD_SET.INITIALIZE_DISC_PUMP, MCU_CONSTANTS.TTP_MAX_PW)
    if result == COMMAND_STATUS.CMD_EXECUTION_ERROR:
        result = fc.send_command_blocking(CMD_SET.INITIALIZE_DISC_PUMP, MCU_CONSTANTS.TTP_MAX_PW)
    if result == COMMAND_STATUS.CMD_EXECUTION_ERROR:
        print("Disc pump failed to initialize")
    return

def pressure_vacuum_test(fc):
    # PRESSURE AND VACUUM TEST
    fc.send_command_blocking(CMD_SET.SET_ROTARY_VALVE, 0, 2)
    fc.send_command_blocking(CMD_SET.SET_ROTARY_VALVE, 1, 2)
    fc.send_command_blocking(CMD_SET.SET_PUMP_PWR_OPEN_LOOP, MCU_CONSTANTS.TTP_MAX_PW)
    fc.send_command_blocking(CMD_SET.DELAY_MS, 500)
    fc.send_command_blocking(CMD_SET.SET_SOLENOID_VALVES, VALVE_POSITIONS.TEST_PRESSURE)
    while fc.recorded_data["pressures"][1] < PRESSURE_TEST:
        fc.get_mcu_status()
    fc.send_command_blocking(CMD_SET.SET_SOLENOID_VALVES, VALVE_POSITIONS.TEST_VACUUM)
    while fc.recorded_data["pressures"][0] > VACUUM_TEST:
        fc.get_mcu_status()
    fc.send_command_blocking(CMD_SET.SET_PUMP_PWR_OPEN_LOOP, 0)
    return
print("Initializing")
initialize_device(fc)
if DO_PRESSURE_VACUUM_TEST:
    print("Testing pressure and vacuum")
    pressure_vacuum_test(fc)

# OPEN LOOP FLUID WITHDRAWAL
print("Clearing lines")
fc.send_command_blocking(CMD_SET.SET_ROTARY_VALVE, 0, 1)
fc.send_command_blocking(CMD_SET.CLEAR_LINES, int((9/9) * MCU_CONSTANTS.TTP_MAX_PW), 3000, 3000)
fc.send_command_blocking(CMD_SET.SET_ROTARY_VALVE, 0, 2)
fc.send_command_blocking(CMD_SET.CLEAR_LINES, int((1/5) * MCU_CONSTANTS.TTP_MAX_PW), 4000, 35000)
fc.send_command_blocking(CMD_SET.SET_SOLENOID_VALVES, VALVE_POSITIONS.FLUID_STOP_FLOW)
print("Re-calibrating bubble sensors now that the lines are clear")
fc.send_command_blocking(CMD_SET.INITIALIZE_BUBBLE_SENSORS)
print("Venting vacuum bottle")
fc.send_command_blocking(CMD_SET.VENT_VB0, -0.1, 20001)
print("Starting load")
fc.send_command_blocking(CMD_SET.SET_ROTARY_VALVE, 0, 1)
fc.send_command_blocking(CMD_SET.LOAD_FLUID_TO_SENSOR, int((3/4) * MCU_CONSTANTS.TTP_MAX_PW), 30000)
print("Vent vacuum bottle")
fc.send_command_blocking(CMD_SET.VENT_VB0, -0.1, 20001)
v = 300
if CTRL == "open":
    print(f"Load {v} uL of fluid open-loop")
    fc.send_command_blocking(CMD_SET.LOAD_FLUID_VOLUME, MCU_CONSTANTS.OPEN_LOOP_CTRL, int((5/11) * MCU_CONSTANTS.TTP_MAX_PW), 30000, v)
    print("Test retention")
    fc.send_command_blocking(CMD_SET.DELAY_MS, 100)
    v = int((3/10) * v)
    print(f"Unload {v} uL of fluid open-loop")
    fc.send_command_blocking(CMD_SET.UNLOAD_FLUID_VOLUME, MCU_CONSTANTS.OPEN_LOOP_CTRL, int((1/30) * MCU_CONSTANTS.TTP_MAX_PW), 30000, v)
elif CTRL == "bb":
    fc.send_command_blocking(CMD_SET.INITIALIZE_BANG_BANG_PARAMS, MCU_CONSTANTS.FLUID_IN_BANG_BANG,  300, 600, 10, 300, 10) # 30 is good option for lower power setpt
    fc.send_command_blocking(CMD_SET.INITIALIZE_BANG_BANG_PARAMS, MCU_CONSTANTS.FLUID_OUT_BANG_BANG, 300, 600, 5, 50,  10)
    print(f"Load {v} uL of fluid bang-bang")
    fc.send_command_blocking(CMD_SET.LOAD_FLUID_VOLUME, MCU_CONSTANTS.FLUID_IN_BANG_BANG, 30000, v)
    print("Test retention")
    fc.send_command_blocking(CMD_SET.DELAY_MS, 100)
    v = int((9/10) * v)
    print(f"Unload {v} uL of fluid bang-bang")
    fc.send_command_blocking(CMD_SET.UNLOAD_FLUID_VOLUME, MCU_CONSTANTS.FLUID_OUT_BANG_BANG, 30000, v)
elif CTRL == "press_pid":
    # Kp, Ki, Kd, intergral winding limit, min/max outputs, and timestep
    fc.send_command_blocking(CMD_SET.INITIALIZE_PID_PARAMS, MCU_CONSTANTS.VACUUM_PID, 1, 0.25, 0.5, MCU_CONSTANTS.ILIM_MAX, 0, MCU_CONSTANTS.TTP_MAX_PW, 20)
    fc.send_command_blocking(CMD_SET.INITIALIZE_PID_PARAMS, MCU_CONSTANTS.PRESSURE_PID, 1, 0.25, 0.5, MCU_CONSTANTS.ILIM_MAX, 0, MCU_CONSTANTS.TTP_MAX_PW, 20)
    print(f"Load {v} uL of fluid with vacuum PID")
    fc.send_command_blocking(CMD_SET.LOAD_FLUID_VOLUME, MCU_CONSTANTS.VACUUM_PID, -0.4, 30000, v)
    print("Test retention")
    fc.send_command_blocking(CMD_SET.DELAY_MS, 100)
    v = int((5/10) * v)
    print(f"Unload {v} uL of fluid with pressure PID")
    fc.send_command_blocking(CMD_SET.UNLOAD_FLUID_VOLUME, MCU_CONSTANTS.PRESSURE_PID, 30000, v)
elif CTRL == "bb/flow":
    fc.send_command_blocking(CMD_SET.INITIALIZE_BANG_BANG_PARAMS, MCU_CONSTANTS.FLUID_IN_BANG_BANG,  1000, 1500, 10, 800, 20) # 0.175
    fc.send_command_blocking(CMD_SET.INITIALIZE_PID_PARAMS, MCU_CONSTANTS.FLUID_OUT_PID, 0.002, 0.006, 0, MCU_CONSTANTS.ILIM_MAX, 0, int((1/5)*MCU_CONSTANTS.TTP_MAX_PW), 20)
    print(f"Load {v} uL of fluid bang-bang")
    fc.send_command_blocking(CMD_SET.LOAD_FLUID_VOLUME, MCU_CONSTANTS.FLUID_IN_BANG_BANG, 30000, v)
    print("Test retention")
    fc.send_command_blocking(CMD_SET.DELAY_MS, 100)
    v = int((5/10) * v)
    print(f"Unload {v} uL of fluid with flowrate PID")
    fc.send_command_blocking(CMD_SET.UNLOAD_FLUID_VOLUME, MCU_CONSTANTS.FLUID_OUT_PID, 1000, 50000, v)
print("Clear extra fluid from the reservoir")
fc.send_command_blocking(CMD_SET.SET_ROTARY_VALVE, 0, 2)
fc.send_command_blocking(CMD_SET.CLEAR_LINES, int(MCU_CONSTANTS.TTP_MAX_PW), 4000, 30000)
fc.send_command_blocking(CMD_SET.SET_ROTARY_VALVE, 0, 1)
print("Eject fluid into open chamber")
fc.send_command_blocking(CMD_SET.EJECT_MEDIUM, int((1/5) * MCU_CONSTANTS.TTP_MAX_PW), 500, 10000, 0.4)
print("Withdraw fluid from open chamber")
fc.send_command_blocking(CMD_SET.REMOVE_ALL_MEDIUM, MCU_CONSTANTS.TTP_MAX_PW, 2000, 10000, 0.6)
# Reset at end
print("resetting")
fc.send_command_blocking(CMD_SET.SET_ROTARY_VALVE, 0, 1)
fc.send_command_blocking(CMD_SET.CLEAR_LINES, int((9/9) * MCU_CONSTANTS.TTP_MAX_PW), 2000, 2000)
fc.send_command_blocking(CMD_SET.SET_ROTARY_VALVE, 0, 2)
fc.send_command_blocking(CMD_SET.CLEAR_LINES, int((2/3) * MCU_CONSTANTS.TTP_MAX_PW), 1000, 35000)
fc.send_command_blocking(CMD_SET.VENT_VB0, -0.3, 20001)
fc.send_command_blocking(CMD_SET.CLEAR)