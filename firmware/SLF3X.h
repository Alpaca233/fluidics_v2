/*
   SLF3X.h
   Contains utilities for running the SLF3X flow sensor.
   https://sensirion.com/media/documents/C4F8D965/65290BC3/LQ_DS_SLF3S-0600F_Datasheet.pdf

   This file contains a class for initializing and reading the sensor, as well as helper functions for translating raw values to Celsius and microliters per minute.

    Created on: 9/13/2022
        Author: Kevin Marx
*/

#ifndef SLF3X_H_
#define SLF3X_H_

#include <Wire.h>
#include <stddef.h>
#include <stdint.h>

// Constants for operation
#define SLF3X_ADDRESS             0x08  // hard-coded address in sensor
#define SLF3X_GEN_RST_ADDRESS     0x00  // send reset signal to this address
#define SLF3X_GEN_RST_CMD         0x06  // command to reset
#define SLF3X_STOP_CTS_MEAS_HIGH  0x3F  // High byte of command to stop continuous measurement
#define SLF3X_STOP_CTS_MEAS_LOW   0xF9  // Low byte
#define SLF3X_START_CTS_MEAS      0x36  // Send this byte followed by one of the two medium select bytes to begin continuous measurement
#define SLF3X_MEDIUM_WATER        0x08  // Use calibration values for water flow measurements
#define SLF3X_MEDIUM_IPA          0x15  // Use calibration values for isopropyl alcohol (IPA)
#define SLF3X_CRC_POLYNOMIAL      0x31  // polynomial for cyclic redundancy check (CRC)

#define SLF3X_SCALE_FACTOR_TEMP   200.0 // 200 per degrees Celsius
#define SLF3X_SCALE_FACTOR_FLOW   10.0  // 10 per (microliter per minute)

#define SLF3X_FLOW_IDX      0     // Where data is stored in readings array
#define SLF3X_TEMP_IDX      1
#define SLF3X_FLAG_IDX      2

#define SLF3X_N_TRIES 10

#define SLF3X_MAX_VAL_uL_MIN 3520 // value saturates at this amount uL/min
#define SLF3X_FS_VAL_uL_MIN  2000 // value accuracy diminishes when flowrate exceeds this threshold

enum SLF3X_SignalFlags_t {
  SLF3X_AIR_IN_LINE  = (1 << 0),
  SLF3X_HIGH_FLOW    = (1 << 1),
  SLF3X_SMOOTHING_ON = (1 << 4)
};

// Function headers
class SLF3X {
  public:
    SLF3X();
    bool begin(TwoWire &W, uint8_t medium, bool do_crc);
    uint8_t read(int16_t *readings);
    bool init;
  private:
    TwoWire *w_;
    bool do_crc_;
};
bool    SLF3X_init(TwoWire &W, uint8_t medium);
uint8_t SLF3X_read(bool do_crc, TwoWire &W, int16_t *readings);
double  SLF3X_to_celsius(int16_t raw_temp);
double  SLF3X_to_uLmin(int16_t raw_flow);

#endif /* SLF3X_H_ */
