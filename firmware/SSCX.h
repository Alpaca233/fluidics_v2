/*
   SSCX.h
   Contains utilities for running the SSCX pressure sensor using either SPI or I2C.
   References:
    - https://prod-edam.honeywell.com/content/dam/honeywell-edam/sps/siot/ja/products/sensors/pressure-sensors/common/documents/sps-siot-spi-comms-digital-ouptu-pressure-sensors-tn-008202-3-en-ciid-45843.pdf
    - https://prod-edam.honeywell.com/content/dam/honeywell-edam/sps/siot/fr-ca/products/sensors/pressure-sensors/board-mount-pressure-sensors/common/documents/sps-siot-i2c-comms-digital-output-pressure-sensors-tn-008201-3-en-ciid-45841.pdf

    Created on: 10/23/2023
        Author: Kevin Marx
*/

#ifndef SSCX_H_
#define SSCX_H_

#include <Wire.h>
#include <SPI.h>
#include <Arduino.h>

// Constants for operation
#define SSCX_ADDRESS    0xFF
#define SSCX_OUT_MIN     1638.0  // 10% of 2^14, we do not expect to see counts below this
#define SSCX_OUT_MAX    14745.0  // 90% of 2^14, we do not expect to see counts above this
#define SSCX_PSI_MAX       15.0  // We are using the SSCMRRV015PD2A3; +- 15 PSI
#define SSCX_PSI_MIN      -15.0
#define SSCX_OUT_SCALE    ((SSCX_PSI_MAX - SSCX_PSI_MIN)/(SSCX_OUT_MAX - SSCX_OUT_MIN)) // macro for counts-to-PSI scale factor
#define SSCX_TEMP_SCALE   (200.0 / 2047.0) // conversion factor for getting the temperature in degrees C
#define SSCX_TEMP_OFFSET  -50.0  // offset factor for getting the temperature in degrees C 
#define SSCX_FLAG_MASK    0b11000000 // mask for the status bits
#define SSCX_LOWTEMP_MASK 0b11100000 // mask for the lower temperature bits
#define SSCX_LOWTEMP_SHIFT         5 // bits to shift the low byte
#define SSCX_HITEMP_SHIFT (8 - SSCX_LOWTEMP_SHIFT) // bits to shift the high byte

enum SSCXStatus_t{
  SSCX_STATUS_NORMAL   = 0b00000000, // normal operation - data is valid
  SSCX_STATUS_CMD_MODE = 0b01000000, // device in "command mode" - should reset
  SSCX_STATUS_STALE    = 0b10000000, // stale data - data is not new
  SSCX_STATUS_DIAGNOST = 0b11000000, // diagnostic condition - EEPROM corrupted
  SSCX_SPI_ERROR       = 0b11111111, // SPI reading failed
  SSCX_I2C_ERROR       = 0b00000001, // I2C generic error - from I2C spec
  SSCX_I2C_FORMAT_ERR  = 0b00000010, // I2C format error - from I2C spec
  SSCX_I2C_DUP_ERR     = 0b00000011, // I2C duplicate transaction error - from I2C spec
  SSCX_I2C_TIMEOUT     = 0b00000100, // I2C timeout error - from I2C spec
  SSCX_I2C_INV_ACQ     = 0b00000101, // I2C Invalid acquirer - from I2C spec
  SSCX_I2C_BAD_USR     = 0b00000110, // I2C bad user - from I2C spec
  SSCX_I2C_MISSING_DAT = 0b00000111, // I2C insufficient data returned
  SSCX_NOT_INITIALIZED = 0b00001000  // SSCX has not been initialized
};

enum SSCXType_t{
  SSCX_I2C,
  SSCX_SPI,
  SSCX_UNINIT
};

// constants for indexing data
#define SSCX_PRESS_IDX    0
#define SSCX_TEMP_IDX     1


class SSCX{
  public:
    SSCX();
    SSCXStatus_t begin(TwoWire &w, uint8_t address);
    SSCXStatus_t begin(SPIClass &s, uint8_t chipsel);
    SSCXStatus_t read(int16_t *readings);
  
  private:
    uint8_t i2c_addr_;
    uint8_t spi_cs_;
    TwoWire *w_;
    SPIClass *s_;
    SSCXType_t type_;
    SPISettings spiSettings_;
};

// Function headers
float   SSCX_to_psi(int16_t raw_press);
int16_t psi_to_SSCX(float psi);
float   SSCX_to_celsius(int16_t raw_temp);

#endif /* SSCX_H_ */
