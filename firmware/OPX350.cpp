/*
    OPX350.cpp
    This file contains functions for initializing and reading from the bubble sensor.

   Class Members:
    Variables:
        uint8_t LOW_A_pin_, HIGH_B_pin_, CALIB_pin_: GPIO pins for reading from and calibrating the sensor
    Functions:
        OPX350: set the private variables
        bool begin: set CALIB_pin_ as output, LOW_A_pin_ and HIGH_B_pin_ as inputs. Always returns true
        bool calibrate: Send a pulse on the CALIB_pin_ and wait for the calibration to finish or until timeout. This is a blocking function.
        uint8_t read: Return the reading on HIGH_B_pin_ on bit 1 and LOW_A_pin_ on bit 0.
*/

#include "OPX350.h"

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: OPX350() initializes the pins

  OPERATION:   Set a flag indiciating the device hasn't been initialized

  ARGUMENTS: None

  RETURNS: None

  INPUTS / OUTPUTS: None

  LOCAL VARIABLES: None

  SHARED VARIABLES:
      bool init_

  GLOBAL VARIABLES: None

  DEPENDENCIES: Arduino.h
  -----------------------------------------------------------------------------
*/
OPX350::OPX350() {
  init_ = false;
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: begin() initializes device

  OPERATION:   Save the pin numbers to local variables and set the input pins as inputs and set the calibration pin high (it is an active low signal)

  ARGUMENTS: 
    uint8_t LOW_A_pin, HIGH_B_pin, CALIB_pin: Pin numbers

  RETURNS: true

  INPUTS / OUTPUTS: Output to the calib pin

  LOCAL VARIABLES: None

  SHARED VARIABLES:
      uint8_t LOW_A_pin, HIGH_B_pin, CALIB_pin
      bool init_

  GLOBAL VARIABLES: None

  DEPENDENCIES: Arduino.h
  -----------------------------------------------------------------------------
*/
bool OPX350::begin(uint8_t LOW_A_pin, uint8_t HIGH_B_pin, uint8_t CALIB_pin) {
  LOW_A_pin_ = LOW_A_pin;
  HIGH_B_pin_ = HIGH_B_pin;
  CALIB_pin_ = CALIB_pin;
  pinMode(LOW_A_pin_, INPUT);
  pinMode(HIGH_B_pin_, INPUT);
  pinMode(CALIB_pin_, OUTPUT);
  digitalWrite(CALIB_pin_, HIGH);
  init_ = true;

  return true;
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: calibrate() sends the calibration signal

  OPERATION:   Send a low pulse on the CALIB line for CALIB_LOW_A_TIME_MS milliseconds.

  ARGUMENTS: None

  RETURNS: bool reading

  INPUTS / OUTPUTS: Output to the calib pin and read from input pins

  LOCAL VARIABLES: uint8_t reading

  SHARED VARIABLES:
      uint8_t CALIB_pin

  GLOBAL VARIABLES: None

  DEPENDENCIES: Arduino.h
  -----------------------------------------------------------------------------
*/
bool OPX350::calibrate() {
  uint8_t reading;
  // Set calib_pin low for a few ms to begin calibration
  digitalWrite(CALIB_pin_, LOW);
  delay(OPX35_CALIB_LOW_PULSE_MS);
  digitalWrite(CALIB_pin_, HIGH);
  return this->read();
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: read() sets the bit 0 if the light is lower than threshold and the bit 1 if the light is above threshold. If the device wasn't configured, only bit 2 is set

  OPERATION:   Check if the device is initialized and return with an error if not. Otherwise

  ARGUMENTS: None

  RETURNS:
    uint8_t result:
          0b000: Light level between upper and lower thresholds (line empty)
          0b001: Light level below threshold (fluid in tube)
          0b010: Light levels above threshold (fluid in tube)
          0b100: Device not configured properly

  INPUTS / OUTPUTS: Read from input pins

  LOCAL VARIABLES: None

  SHARED VARIABLES:
      uint8_t LOW_A_pin, HIGH_B_pin, CALIB_pin
      bool init_

  GLOBAL VARIABLES: None

  DEPENDENCIES: Arduino.h
  -----------------------------------------------------------------------------
*/
OPX350_READINGS OPX350::read() {

  if (init_ == false)
    return OPX350_ERR;

  return (!digitalRead(HIGH_B_pin_) << 1) | (!digitalRead(LOW_A_pin_));
}
