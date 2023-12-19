/*
    SSCX.cpp
    This file contains a class and functions for initializing and reading from the pressure sensor.

    SSCX Class:
      SSCX(): Sets up the class. No arguments or returns
      begin(): Initializes either SPI or I2C - this function is overloaded
        Arguments: TwoWire &W, uint8_t address
        Returns: I2C error code if there was an error, otherwise returns status bits
        Arguments: SPIClass &s, uint8_t chipsel
        Returns: SSCXStatus_t error
      SSCX_read(): Read a value from the sensor into the shared readings variable. Returns flags indicating specific failures in the reading process.
        Arguments: int16_t *readings
        Returns: SSCXStatus_t error

    Misc. Functions (not part of class):
      float SSCX_to_celsius: Convert from raw to degrees Celsius
        Arguments: int16_t raw_temp
      float SSCX_to_psi: Convert from raw to pounds per square inch
        Arguments: int16_t raw_press

    Created on: 10/23/2023
        Author: Kevin Marx
*/
#include "SSCX.h"

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: SSCX() initializes the class
  OPERATION:   None

  ARGUMENTS:   None

  RETURNS: NONE

  INPUTS / OUTPUTS: NONE

  LOCAL VARIABLES: NONE

  SHARED VARIABLES: NONE

  GLOBAL VARIABLES: None

  DEPENDENCIES: None
  -----------------------------------------------------------------------------
*/
SSCX::SSCX() {
  type_ = SSCX_UNINIT;
  return;
}
/*
  -----------------------------------------------------------------------------
  DESCRIPTION: This verison of begin() initializes the I2C communications with the device.

  OPERATION:   We store the I2C address into a shared variable and begin communications with the sensor. We also set the type of sensor to I2C. We then try reading from the sensor and return its error value.

  ARGUMENTS:
    TwoWire &w: Pointer to I2C object
    uint8_t address: Address of sensor

  RETURNS:
    SSCXStatus_t error: Status of sensor. If there was an I2C communication error, we return the I2C error code. If we were able to read from the sensor, return the sensor's status

  INPUTS / OUTPUTS:
    We send and receive signals over I2C

  LOCAL VARIABLES:
    uint16_t* reading: Reading value. Used to perform a reading

  SHARED VARIABLES:
    TwoWire *w_:       We set the pointer to the TwoWire object
    uint8_t i2c_addr_: We set the address to the I2C sensor
    SSCXType_t type_:    We set the sensor type to I2C

  GLOBAL VARIABLES: None

  DEPENDENCIES:
    Arduino.h
    Wire.h
  -----------------------------------------------------------------------------
*/
SSCXStatus_t SSCX::begin(TwoWire &w, uint8_t address) {
  // Initialize variables
  int16_t readings[2];
  // Set sensor type
  type_ = SSCX_I2C;
  // Initialize I2C
  w_ = &w;
  i2c_addr_ = address;
  w_->begin();

  return this->read(readings);
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: This verison of begin() initializes the SPI communications with the device.

  OPERATION:   We store the SPI CS into a shared variable and begin communications with the sensor. We also set the type of sensor to SPI. We then try reading from the sensor and return its error value.

  ARGUMENTS:
    SPIClass &s: Pointer to SPI object
    uint8_t chipsel: Chip select pin

  RETURNS:
    SSCXStatus_t error: Status of sensor. If there was an SPI communication error, we return 0xFF. If we were able to read from the sensor, return the sensor's status

  INPUTS / OUTPUTS:
    We send and receive signals over SPI

  LOCAL VARIABLES:
    uint16_t* reading: Reading value. Used to perform a reading

  SHARED VARIABLES:
    SPIClass &s:       We set the pointer to the SPI object
    uint8_t spi_cs_:   We set the chip select pin of the sensor
    SSCXType_t type_:    We set the sensor type to SPI

  GLOBAL VARIABLES: None

  DEPENDENCIES:
    Arduino.h
    SPI.h
  -----------------------------------------------------------------------------
*/
SSCXStatus_t SSCX::begin(SPIClass &s, uint8_t chipsel) {
  // Initialize variables
  int16_t readings[2];
  // Set sensor type
  type_ = SSCX_SPI;
  // Initialize SPI
  s_ = &s;
  s_->begin();
  spi_cs_ = chipsel;
  pinMode(spi_cs_, OUTPUT);
  digitalWrite(spi_cs_, HIGH);
  spiSettings_ = SPISettings(800000, MSBFIRST, SPI_MODE0);

  return this->read(readings);
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: read() reads the raw pressure, temperature, and flags from the sensor over I2C or SPI. The flags are returned and the pressure and temperature are written to a shared array

  OPERATION:   We request 4 uint8_ts from the sensor, status and pressure_high, pressure_low, temp_high, and temp_low. The status bits are returned as part of the flags while the pressure and temperature data is stored in the shared readings array.

  ARGUMENTS:
      int16_t *readings: Pointer to array for storing data. The data at this array will be overwritten.

  RETURNS:
      SSCXStatus_t status

  INPUTS / OUTPUTS: The I2C or SPI lines are used as inputs and outputs to transmit data

  LOCAL VARIABLES: None

  SHARED VARIABLES:
     int16_t readings[2]: Used to store the data. We are writing to this array.
        readings[0]: raw pressure value
        readings[1]: raw temperature value
     uint8_t i2c_addr_: I2C address of sensor
     uint8_t spi_cs_:   Chip select pin of sensor
     TwoWire *w_:       I2C bus
     SPIClass *s_:      SPI bus
     SSCXType_t type_:    Whether to use SPI or I2C

  GLOBAL VARIABLES: None

  DEPENDENCIES: Wire.h
  -----------------------------------------------------------------------------
*/
SSCXStatus_t SSCX::read(int16_t *readings) {
  uint8_t    rx[4];   // store raw data
  uint8_t    err = 0; // assume no error

  // If we haven't initialized, return an error
  if (type_ == SSCX_UNINIT)
    return SSCX_NOT_INITIALIZED;

  // put default values in readings[]
  for (uint8_t i = 0; i < 2; i++) {
    readings[i] = INT16_MAX;
  }
    
  if (type_ == SSCX_I2C) {
    w_->requestFrom(i2c_addr_, (uint8_t)4);
    delayMicroseconds(3);
    // Return with error if we fail to read all the uint8_ts
    if (w_->available() < 4) {
      return SSCX_I2C_MISSING_DAT;
    }

    // Read all the data
    for (uint8_t i = 0; i < 4; i++){
      rx[i] = w_->read();
    }
  }
  else{
    //do SPI reading into rx[]
    s_->beginTransaction(spiSettings_);
    digitalWrite(spi_cs_, LOW);
    delayMicroseconds(3);
    s_->transfer(rx, (uint8_t)4);
    digitalWrite(spi_cs_, HIGH);
    s_->endTransaction();
  }

  // format the err bits
  err |= (rx[0] & SSCX_FLAG_MASK);
  // get the raw pressure
  readings[0] = ((rx[0] & ~SSCX_FLAG_MASK) << 8 );
  readings[0] |= rx[1];
  // get the raw temperature
  readings[1] = rx[2] << SSCX_HITEMP_SHIFT;
  rx[3] = rx[3] >> SSCX_LOWTEMP_SHIFT;
  readings[1] |= rx[3];
  return (SSCXStatus_t)err;
}


/*
  -----------------------------------------------------------------------------
  DESCRIPTION: SSCX_to_celsius() converts from a raw sensor reading to degrees Celsius

  OPERATION:   We multiply the raw value by the scale value, add an offset, and return it

  ARGUMENTS:
      int16_t  raw_temp: raw temperature value from the sensor

  RETURNS:
      float temp:         temperature in degrees Celsius

  INPUTS / OUTPUTS: None

  LOCAL VARIABLES: None

  SHARED VARIABLES: None

  GLOBAL VARIABLES: None

  DEPENDENCIES: None
  -----------------------------------------------------------------------------
*/
float SSCX_to_celsius(int16_t raw_temp) {
  return (raw_temp * SSCX_TEMP_SCALE) + SSCX_TEMP_OFFSET;
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: SSCX_to_psi() converts from a raw sensor reading to pounds per square inch

  OPERATION:   We offset the raw value, scale it, then offset it again

  ARGUMENTS:
      int16_t  raw_press: raw pressure value from the sensor

  RETURNS:
      float pressure:     pressure in PSI

  INPUTS / OUTPUTS: None

  LOCAL VARIABLES: None

  SHARED VARIABLES: None

  GLOBAL VARIABLES: None

  DEPENDENCIES: None
  -----------------------------------------------------------------------------
*/
float SSCX_to_psi(int16_t raw_press) {
  float pressure = constrain(raw_press, SSCX_OUT_MIN, SSCX_OUT_MAX);
  return (pressure * SSCX_OUT_SCALE) + SSCX_PSI_MIN;
}

int16_t psi_to_SSCX(float psi) {
  float intermediate = (psi - SSCX_PSI_MIN) / (SSCX_OUT_SCALE);
  return constrain(intermediate, SSCX_OUT_MIN, SSCX_OUT_MAX);
}
