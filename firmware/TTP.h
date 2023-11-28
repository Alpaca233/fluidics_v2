/*
   TTP.h
   Contains utilities for running the TTP disc pump.

   This class implements the following features: 
      - Initialization
      - Enable/Disable
      - Set output power
      - Get status

    Created on: 9/15/2022
        Author: Kevin Marx
*/

#ifndef TTP_H_
#define TTP_H_

#include <stddef.h>
#include <stdint.h>
#include <Arduino.h>
#include <float.h>

// Constants for operation
// Register map
enum TTPRegisterMap_t{
  TTP_ERR_CODE        = 31,
  TTP_SET_VALUE       = 23,
  TTP_MANUAL_SRC      = 11,
  TTP_CTRL_MODE       = 10,
  TTP_DRV_FREQ        =  6,
  TTP_DRV_PWR         =  5,
  TTP_DRV_CURRENT     =  4,
  TTP_DRV_VOLT        =  3,
  TTP_STREAM_MODE     =  2,
  TTP_PWR_LIMIT       =  1,
  TTP_ENABLED         =  0
};
// Fields
enum TTPFields_t{
  TTP_SRC_SETVAL      =  0,
  TTP_MODE_MANUAL     =  0,
  TTP_STREAM_DISABLE  =  0,
  TTP_PUMP_ENABLE     =  1,
  TTP_PUMP_DISABLE    =  0
};

#define TTP_MIN_PWR          0.0
#define TTP_MAX_PWR       1000.0

#define TTP_BAUDRATE        115200 // disc pump baud rate
#define TTP_BUFFER_SIZE         32 // 32 byte read/write buffer
#define TTP_N_TRIES              3 // Try reading/writing 3 times
#define TTP_READ_TIMEOUT_mS   2000 // wait this many microseconds before timing out
#define TTP_IDLETIME_uS        300 // wait this many microseconds while idling

#define TTP_INT_READ_ERR INT16_MIN
#define TTP_FLT_READ_ERR FLT_MAX

#define TTP_READ_REG_FORMAT    "#R%d\n"      // string format for reading a register
#define TTP_WR_REG_INT_FORMAT  "#W%d,%d\n"   // string format for writing to a register
#define TTP_WR_REG_FLT_FORMAT  "#W%d,%.8f\n" // string format for writing to a register. Change the 8 to the number of digits you want past the decimal

class TTP{
  public:
    TTP();
    bool begin(HardwareSerial &s);
    bool init(int16_t pwr_lim, uint8_t src, uint8_t mode, uint8_t stream);
    bool enable(bool en);
    bool set_pwr_limit(int16_t pwr_lim);
    bool set_target(float target);
    bool get_status(int16_t &error_code, int16_t &drive_freq, float &drive_pwr, float &drive_current, float &drive_voltage, float &power_limit);
    int16_t read_int(TTPRegisterMap_t reg);
    float read_float(TTPRegisterMap_t reg);
    float pwr;
  private:
    bool send_packet(char *tx_buffer, char *rx_buffer);
    bool write_register(TTPRegisterMap_t reg, float dat);
    bool write_register(TTPRegisterMap_t reg, int16_t dat);
    HardwareSerial *s_;
    bool init_;
    
};

#endif /* TTP_H_ */
