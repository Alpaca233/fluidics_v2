/*
  This file implements Serial control over the fluidics controller and maintains the control loop.

*/

#include "AutoPID.h"
#include "NXP33996.h"
#include "OPX350.h"
#include "RheoLink.h"
#include "SLF3X.h"
#include "TTP.h"
#include "SSCX.h"
#include "_defs.h"
#include <PacketSerial.h>

// Class constructors and supporting global variables/definitions for the different modules we want
// TODO: Move #defines to a separate file to support different hardware configs

// Closed loop control: Use bang-bang to get fluid into the reservior (positive) and bang-bang / PID to get fluid out (negative)
// Need different params for input vs output due to fluidics topology
double global_flowrate_reading = 0;
double global_power_out = 0;
double global_pid_setpoint = 0;
AutoBangBang fluid_in_bb(&global_flowrate_reading, &global_power_out, +1);
AutoBangBang fluid_out_bb(&global_flowrate_reading, &global_power_out, -1);
AutoPID fluid_out_pid(&global_flowrate_reading, &global_pid_setpoint, &global_power_out, -1);

// NXP33996 - valve controller
//#define VALVES_RST 10
//#define VALVES_CS   2
//#define VALVES_PWM  3
NXP33996 valves;

// OPX350 - bubble sensors
//#define FLUIDSENSORFRONT_A 27
//#define FLUIDSENSORFRONT_B 26
//#define FLUIDSENSORFRONT_C 31
//
//#define FLUIDSENSORBACK_A  28
//#define FLUIDSENSORBACK_B  28
//#define FLUIDSENSORBACK_C  30
OPX350 fluidsensor_front, fluidsensor_back;

// Selector valves
//#define SELECTORVALVE_WIRE Wire
//#define SELECTORVALVE_MAX  5     // Support up to 5 valves
//#define SELECTORVALVE_QTY  2     // Only 2 are actually installed here
//const uint8_t SELECTORVALVE_ADDRS[] = {0x1E, 0x0E, 0x00, 0x00, 0x00}; // 0x00 is dummy address
RheoLink selectorvalves[SELECTORVALVE_QTY];

// SLF3X flowrate sensor
//#define SLF3X_WIRE0   Wire
//#define SLF3X_WIRE1   Wire1
//#define SLF3X_WIRE2   Wire2
//#define PERFORM_CRC  true
SLF3X flowsensor;

// SSCX pressure sensors
//#define SSCX_SPI     SPI
//#define SSCX_MAX      4 // Support up to 4 pressure sensors
//#define SSCX_QTY      2 // Only 2 are installed here
//const uint8_t PRESSURE_CS[] = {37, 36, 35, 34}; // Only index 0 and 1 are populated on most boards
SSCX pressuresensors[SSCX_QTY];

// TTP Disc Pump
//#define TTP_UART             Serial3
//#define TTP_SELECTED_MODE    TTP_MODE_MANUAL
//#define TTP_SELECTED_STREAM  TTP_STREAM_DISABLE
//#define TTP_SELECTED_SRC     TTP_SRC_SETVAL
//#define TTP_PWR_LIM_mW       TTP_MAX_PWR
TTP discpump;

// PacketSerial
PacketSerial pSerial;

// Timekeeping
uint32_t tx_interval_ms = TX_INTERVAL_MS;
elapsedMillis time_since_last_tx = 0;
elapsedMillis time_since_cmd_started = 0;
elapsedMillis time_since_last_sensor = 0;

// Track state
InternalState_t    state;
CommandExecution_t execution_status;
uint16_t           cmd_uid;
SerialCommands_t   cmd_rxed;
double             integrated_volume_uL;

void setup() {
  // Initialize serial communications with the host computer
  pSerial.begin(2000000);
  pSerial.setPacketHandler(&onPacketReceived);

  state = INTERNAL_STATE_IDLE;
  execution_status = COMPLETED_WITHOUT_ERRORS;
}

void loop() {
  // Update control loops, pSerial
  pSerial.update();
  fluid_in_bb.run();
  fluid_out_bb.run();
  fluid_out_pid.run();

  // If sufficient time elapsed, send status packet back
  if (time_since_last_tx > tx_interval_ms) {
    time_since_last_tx -= tx_interval_ms;
    sendStatusPacket();
  }

  // State machine for performing multi-step operations
  switch (state) {
    case INTERNAL_STATE_IDLE:
      break;
  }
}

void sendStatusPacket() {
  /*
        #########################################################
        #########   MCU -> Computer message structure   #########
        #########################################################
        byte 0-1    : computer -> MCU CMD counter (UID)
        byte 2      : cmd from host computer (error checking through check sum => no need to transmit back the parameters associated with the command)
        byte 3      : status of the command (see _def.py)
        byte 4      : MCU internal program being executed (see _def.py)
        byte 5      : Bubble sensor state (high and low nibble)
        byte 6-10   : Selector valves status (1,2,3,4,5)
        byte 11-12  : state of valve D1-D16
        byte 13-14  : pump power
        byte 15-16  : pressure sensor 1 reading
        byte 17-18  : pressure sensor 2 reading
        byte 19-20  : pressure sensor 3 reading
        byte 21-22  : pressure sensor 4 reading
        byte 23-24  : flow sensor 1 reading
        byte 25-26  : flow sensor 2 reading
        byte 27     : elapsed time since the start of the last internal program (in seconds)
        byte 28-29  : total volume (ul), range: 0 - 5000
  */

  byte buffer_tx[FROM_MCU_MSG_LENGTH];
  buffer_tx[0] = byte(cmd_uid >> 8);
  buffer_tx[1] = byte(cmd_uid & 0xFF);

  buffer_tx[2] = cmd_rxed;
  buffer_tx[3] = execution_status;
  buffer_tx[4] = state;

  uint8_t fs1 = fluidsensor_front.read();
  uint8_t fs2 = fluidsensor_back.read();
  buffer_tx[5] = byte((fs1 << 4) | fs2);

  // Read from selector valves
  for (uint8_t i = 0; i < SELECTORVALVE_QTY; i++) {
    buffer_tx[6 + i] =  byte(selectorvalves[i].read_register(RheoLink_STATUS));
  }
  // Fill remaining entries of buffer with 0
  for (uint8_t i = SELECTORVALVE_QTY; i < SELECTORVALVE_MAX; i++) {
    buffer_tx[6 + i] = 0;
  }

  buffer_tx[11] =  byte(valves.local_state >> 8);
  buffer_tx[12] =  byte(valves.local_state & 0xFF);

  uint16_t normed_power = (discpump.pwr / TTP_MAX_PWR) * UINT16_MAX;
  buffer_tx[13] = byte(normed_power >> 8);
  buffer_tx[14] = byte(normed_power & 0xFF);

  // Get pressure readings
  int16_t press_readings[2];
  for (uint8_t i = 0; i < SSCX_QTY; i++) {
    pressuresensors[i].read(press_readings);
    buffer_tx[15 + (2 * i)] = byte(press_readings[SSCX_PRESS_IDX] >> 8);
    buffer_tx[16 + (2 * i)] = byte(press_readings[SSCX_PRESS_IDX] && 0xFF);
  }
  for (uint8_t i = SSCX_QTY; i < SSCX_MAX; i++) {
    buffer_tx[15 + (2 * i)] = 0;
    buffer_tx[16 + (2 * i)] = 0;
  }

  int16_t flow_readings[3];
  flowsensor.read(flow_readings);
  buffer_tx[23] = byte(flow_readings[SLF3X_FLOW_IDX] >> 8);
  buffer_tx[24] = byte(flow_readings[SLF3X_FLOW_IDX] & 0xFF);

  buffer_tx[25] = 0; // We don't have a second flow sensor
  buffer_tx[26] = 0;

  buffer_tx[27] = byte(time_since_cmd_started / 1000);

  int16_t volume_ul_int16 = (integrated_volume_uL / VOLUME_UL_MAX) * INT16_MAX;
  buffer_tx[28] = byte(volume_ul_int16 >> 8);
  buffer_tx[29] = byte(volume_ul_int16 & 0xFF);

  pSerial.send(buffer_tx, FROM_MCU_MSG_LENGTH);

  return;
}


// We process the incoming command here
void onPacketReceived(const uint8_t* buffer, size_t size) {
  // If we don't have enough bytes, return out before having a buffer overflow
  if (size < 3) {
    return;
  }
  // Get the received command
  cmd_rxed = buffer[0];
  // Get the cmd uid
  cmd_uid = (buffer[1] << 8) + buffer[2];
  switch (cmd_rxed) {
    case CLEAR: {
        // Stop all operations
        fluid_in_bb.stop();
        fluid_out_bb.stop();
        fluid_out_pid.stop();
        valves.clear_all();
        for (uint8_t i = 0; i < SELECTORVALVE_QTY; i++) {
          selectorvalves[i].send_command(RheoLink_POS, 1);
        }
        discpump.set_target(0);
        discpump.enable(false);

        time_since_last_tx = 0;
        time_since_cmd_started = 0;
        time_since_last_sensor = 0;

        state = INTERNAL_STATE_IDLE;
        execution_status = COMPLETED_WITHOUT_ERRORS;
        cmd_uid = 0;
        integrated_volume_uL = 0;
      }
      break;

    case INITIALIZE_DISC_PUMP: {
        // Ensure the correct amount of data was sent
        // If we don't see exactly 8 bytes, don't do anything
        // 3 bytes for cmd and UID, 5 for initializing the pump
        if (size !=  8) {
          state = INTERNAL_STATE_IDLE;
          execution_status = CMD_INVALID;
          return;
        }
        // Ensure the control loops are stopped
        fluid_in_bb.stop();
        fluid_out_bb.stop();
        fluid_out_pid.stop();
        // Initialize variables
        int16_t pwr_lim = int16_t((buffer[3] << 8) + buffer[4]);
        uint8_t src = buffer[5];
        uint8_t mode = buffer[6];
        uint8_t stream = buffer[7];
        // Begin initialization
        discpump.begin(TTP_UART);
        bool result = discpump.init(pwr_lim, src, mode, stream);
        // Ensure disc pump is not enabled
        discpump.set_target(0);
        discpump.enable(false);

        if (result) {
          execution_status = COMPLETED_WITHOUT_ERRORS;
        }
        else {
          execution_status = COMPLETED_WITHOUT_ERRORS;
        }
        state = INTERNAL_STATE_IDLE;
      }
      break;

    case INITIALIZE_PRESSURE_SENSOR: {
        // Ensure the correct amount of data was sent
        // If we don't see exactly 4 bytes, don't do anything
        // 3 bytes for cmd and UID, 1 for initializing the pump
        if (size !=  4) {
          state = INTERNAL_STATE_IDLE;
          execution_status = CMD_INVALID;
          return;
        }
        uint8_t idx = buffer[3];
        SSCXStatus_t result;
        if (idx < SSCX_QTY) {
          result = pressuresensors[idx].begin(SPI, PRESSURE_CS[idx]);
        }
        else {
          state = INTERNAL_STATE_IDLE;
          execution_status = CMD_INVALID;
          return;
        }

        if (result == SSCX_STATUS_NORMAL) {
          execution_status = COMPLETED_WITHOUT_ERRORS;
        }
        else {
          execution_status = COMPLETED_WITHOUT_ERRORS;
        }
        state = INTERNAL_STATE_IDLE;
      }
      break;

    case INITIALIZE_FLOW_SENSOR: {
        // Ensure the correct amount of data was sent
        // If we don't see exactly 6 bytes, don't do anything
        // 3 bytes for cmd and UID, 3 for initializing the sensor
        if (size !=  6) {
          state = INTERNAL_STATE_IDLE;
          execution_status = CMD_INVALID;
          return;
        }
        uint8_t medium = buffer[4];
        bool do_crc = buffer[5];
        bool result;
        if (buffer[3] == 0) {
          result = flowsensor.begin(SLF3X_WIRE0, medium, do_crc);
        }
        else if (buffer[3] == 1) {
          result = flowsensor.begin(SLF3X_WIRE1, medium, do_crc);
        }
        else if (buffer[3] == 2) {
          result = flowsensor.begin(SLF3X_WIRE2, medium, do_crc);
        }
        else {
          state = INTERNAL_STATE_IDLE;
          execution_status = CMD_INVALID;
          return;
        }

        if (result) {
          execution_status = COMPLETED_WITHOUT_ERRORS;
        }
        else {
          execution_status = COMPLETED_WITHOUT_ERRORS;
        }
        state = INTERNAL_STATE_IDLE;
      }

      break;

    case INITIALIZE_BUBBLE_SENSORS: {
        // We no additional data - all hard-coded
        if (size != 3) {
          state = INTERNAL_STATE_IDLE;
          execution_status = CMD_INVALID;
          return;
        }
        fluidsensor_front.begin(FLUIDSENSORFRONT_A, FLUIDSENSORFRONT_B, FLUIDSENSORFRONT_C);
        fluidsensor_back.begin(FLUIDSENSORBACK_A, FLUIDSENSORBACK_B, FLUIDSENSORBACK_C);

        bool calibrated = true;
        calibrated &= fluidsensor_front.calibrate();
        calibrated &= fluidsensor_back.calibrate();
        if (calibrated) {
          execution_status = COMPLETED_WITHOUT_ERRORS;
        }
        else {
          execution_status = COMPLETED_WITHOUT_ERRORS;
        }
        state = INTERNAL_STATE_IDLE;
      }
      break;

    case INITIALIZE_VALVES: {
        // We no additional data - all hard-coded
        if (size != 3) {
          state = INTERNAL_STATE_IDLE;
          execution_status = CMD_INVALID;
          return;
        }
        valves.begin(VALVES_CS, VALVES_PWM, VALVES_RST, VALVES_SPI);
        execution_status = COMPLETED_WITHOUT_ERRORS;
        state = INTERNAL_STATE_IDLE;
      }
      break;

    case INITIALIZE_BANG_BANG_PARAMETERS: {
        // Ensure the correct amount of data was sent
        // If we don't see exactly 15 bytes, don't do anything
        // 3 bytes for cmd and UID, 12 for initializing the controller
        double t_low, t_high, o_min, o_max;
        uint32_t tstep;
        
        t_low  = (((buffer[3] << 8) + buffer[4]) / INT16_MAX) * SLF3X_MAX_VAL_uL_MIN;
        t_high = (((buffer[5] << 8) + buffer[6]) / INT16_MAX) * SLF3X_MAX_VAL_uL_MIN;
        setThresholds(t_low, t_high);
        o_min = (((buffer[7] << 8) + buffer[8]) / INT16_MAX) * TTP_PWR_LIM_mW;
        o_max = (((buffer[9] << 8) + buffer[10]) / INT16_MAX) * TTP_PWR_LIM_mW;
        setOutputRange(o_min, o_max);
        tstep = (buffer[11] << (8 * 3)) + (buffer[12] << (8 * 2)) + (buffer[13] << 8) + buffer[14];
        setTimeStep(tstep);
        
        execution_status = COMPLETED_WITHOUT_ERRORS;
        state = INTERNAL_STATE_IDLE;
      }
      break;

    case INITIALIZE_PID_PARAMETERS: {
        // Ensure the correct amount of data was sent
        // If we don't see exactly 19 bytes, don't do anything
        // 3 bytes for cmd and UID, 16 for initializing the controller
        double kp, ki, kd, ilim;
        double o_min, o_max;
        uint32_t tstep;
        kp   = (((buffer[3] << 8) + buffer[4])  / INT16_MAX) * KP_MAX;
        ki   = (((buffer[5] << 8) + buffer[6])  / INT16_MAX) * KI_MAX;
        kd   = (((buffer[7] << 8) + buffer[8])  / INT16_MAX) * KD_MAX;
        ilim = (((buffer[9] << 8) + buffer[10]) / INT16_MAX) * ILIM_MAX;
        setGains(kp, ki, kd, ilim);
        o_min = (((buffer[11] << 8) + buffer[12]) / INT16_MAX) * TTP_PWR_LIM_mW;
        o_max = (((buffer[13] << 8) + buffer[14]) / INT16_MAX) * TTP_PWR_LIM_mW;
        setOutputRange(o_min, o_max);
        tstep = (buffer[15] << (8 * 3)) + (buffer[16] << (8 * 2)) + (buffer[17] << 8) + buffer[18];
        setTimeStep(tstep);

        execution_status = COMPLETED_WITHOUT_ERRORS;
        state = INTERNAL_STATE_IDLE;
      }
      break;

    default:
      state = INTERNAL_STATE_IDLE;
      execution_status = CMD_INVALID;
      break;
  }
  return;
}
