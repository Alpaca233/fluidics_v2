/* NXP33996.cpp
   Implement NXP33996 Class
   https://www.nxp.com/products/power-management/smart-switches-and-drivers/low-side-switches/16-output-switch-with-spi-control:MC33996
   16-Output Switch with SPI Control
   This does not implement all the features of the NXP33996, just simple on/off control.

   This class implements the folowing features:
        - Initialization
        - Write arbitrary 16 bits to the outputs
        - Set select bit
        - Clear select bit
        - Clear all bits
        - Get current state

   Class Members:
    Variables:
        uint8_t CS_pin, PWM_pin, RST_pin: GPIO pins for chip select (active low), PWM control, and reset respectively
        uint16_t local_state: state of all 16 outputs
    Functions:
        NXP33996: set the CS, PWM, RST  private variables
          Arguments: uint8_t cs_pin, pwm_pin, rst_pin: Pin numbers of CS, PWM, RST respectively. CS and RST are active-low
          Returns: None
          Shared Variables: CS_pin, PWM_pin, RST_pin are initialized with the arguments and internal_state is initialized to 0
          Inputs/Outputs: None
        bool begin: Sets the pins as outputs and initializes SPI
          Arguments: None
          Returns: Returns true if initialized successfully, otherwise return false
          Shared Variables: CS_pin, RST_pin, PWM_pin are accessed
          Inputs/Outputs: Initializes SPI bus with parameters for the NXP33996 and sets the CS, PWM, RST pins as outputs
        uint16_t transfer: overwrite all 16 outputs with uint16_t id and return the previous state
          Arguments: uint16_t id: the 16 outputs to write to the NXP33996
          Returns: uint16_t result: the previous state of the NXP33996
          Shared Variables: local_state is overwritten with id
          Inputs/Outputs: data is sent over the SPI bus
        void clear_all: reset all 16 outputs
          Arguments/Returns: None
          Shared Variables: local_state is overwritten with 0
          Inputs/Outputs: data is sent over the SPI bus
        void turn_on: set specific outputs without modifying the others
          Arguments: uint8_t id: bit number to set
          Returns: none
          Shared Variables: local_state is overwritten with new state
          Inputs/Outputs: data is sent over the SPI bus
        void turn_off: reset specifi outputs without modifying others
          Arguments: uint8_t id: bit number to clear
          Returns: none
          Shared Variables: local_state is overwritten with new state
          Inputs/Outputs: data is sent over the SPI bus

    Dependencies:
      SPI.h, Arduino.h: For SPI and GPIO operations
*/

#include "NXP33996.h"


/*
  -----------------------------------------------------------------------------
  DESCRIPTION: NXP33996() initializes the local_state private variable.

  OPERATION:   We set local_state to 0.

  ARGUMENTS: None

  RETURNS: NONE

  INPUTS / OUTPUTS: NONE

  LOCAL VARIABLES: None

  SHARED VARIABLES:
     uint16_t local_state: Write state of the NXP33996

  GLOBAL VARIABLES: None

  DEPENDENCIES: None
  -----------------------------------------------------------------------------
*/
NXP33996::NXP33996() {
  // Initialize variables
  local_state = 0;
  init_ = false;
  return;
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: begin() sets the CS, PWM, RST pins as outputs and initializes SPI

  OPERATION:   First, set the CS, PWM, and RST private variables. We pinMode() the CS, PWM, RST pins and initialize the SPI bus per the datasheet specification, and set CS, RST pins high (they are active-low).
               Also set flag indicating it has initialized properly.

  ARGUMENTS: NONE

  RETURNS: bool success: Set true if the initialization succeeds

  INPUTS:  NONE

  OUTPUTS: GPIO pins are set as outputs, SPI bus is initialized
           CS_pin and RST_pin are set HIGH

  LOCAL VARIABLES: None

  SHARED VARIABLES:
     uint8_t CS_pin, PWM_pin, RST_pin: Read GPIO pin numbers, written to and read from
     SPISettings spiSettings_: SPI settings
     SPIClass *s_:      SPI bus
     bool init_:        Indicates the device has been initialized

  GLOBAL VARIABLES: None

  DEPENDENCIES: SPI.h
  -----------------------------------------------------------------------------
*/
bool NXP33996::begin(uint8_t cs_pin, uint8_t pwm_pin, uint8_t rst_pin, SPIClass  &s) {
  // Initialize shared vars
  CS_pin = cs_pin;
  PWM_pin = pwm_pin;
  RST_pin = rst_pin;
  s_ = &s;
  s_->begin();
  // Set outputs
  pinMode(CS_pin, OUTPUT);
  pinMode(PWM_pin, OUTPUT);
  pinMode(RST_pin, OUTPUT);
  // Initialize SPI Communications
  spiSettings_ = SPISettings(6000000, MSBFIRST, SPI_MODE1);
  // Set active-low pins HIGH
  digitalWrite(CS_pin, HIGH);
  digitalWrite(RST_pin, HIGH);

  init_ = true;

  return true;
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: transfer() overwrites the device output with the 16 bit argument and returns the previous state of the device.

  OPERATION:   First, if we haven't init yet, do nothing. Otherwise, we overwrite local_state with our target state. We next initialize the SPI transfer by pulling CS_pin low, sending the on/off control command, then transferring the 16 bit new pattern.The NXP33996 responds with the previous 16 bit state it had which it then , then we write CS high.

  ARGUMENTS: uint16_t id: 16 bit value to write

  RETURNS: uint16_t result: 16 bit prior state of the device

  INPUTS:  Data is received over the SPI bus

  OUTPUTS: Data is sent over the SPI bus, the CS pin is brought low during the SPI operation

  LOCAL VARIABLES: None

  SHARED VARIABLES:
     uint8_t CS_pin: Read GPIO pin numbers
     uint16_t local_state: Overwritten by the argument
     SPISettings spiSettings_: SPI settings
     SPIClass *s_:      SPI bus

  GLOBAL VARIABLES: None

  DEPENDENCIES: SPI.h
  -----------------------------------------------------------------------------
*/
uint16_t NXP33996::transfer(uint16_t id) {
  uint16_t result;

  if(!init_){
    return 0;
  }
  
  local_state = id;
  s_->beginTransaction(spiSettings_);
  digitalWrite(CS_pin, LOW);
  delayMicroseconds(3);
  s_->transfer(ON_OFF_CTRL);
  result = s_->transfer16(local_state); //16 output bits
  digitalWrite(CS_pin, HIGH);
  s_->endTransaction();

  return result;
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: clear_all() transfers 0x0000 to the device and overwrites the local_state with 0x0000

  OPERATION:   We first overwrite local_state with 0x0000. We next call this->transfer and transfer the local_state

  ARGUMENTS/RETURNS: NONE

  INPUTS:  NONE

  OUTPUTS: Data is sent over the SPI bus, the CS pin is brought low during the SPI operation

  LOCAL VARIABLES: None

  SHARED VARIABLES:
     uint8_t CS_pin: Read GPIO pin numbers
     uint16_t local_state: Overwritten with 0x0000

  GLOBAL VARIABLES: None

  DEPENDENCIES: SPI.h
  -----------------------------------------------------------------------------
*/
void NXP33996::clear_all() {
  local_state = 0;
  this->transfer(local_state);
  return;
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: turn_on() sets a bit in local_state and writes local_state to the device.

  OPERATION:   We first OR local_state with 0x01 shifted left by id. This sets our target bit in local_state. We next call this->transfer and transfer the local_state

  ARGUMENTS: uint8_t id: which bit to set high

  RETURNS: NONE

  INPUTS:  NONE

  OUTPUTS: Data is sent over the SPI bus, the CS pin is brought low during the SPI operation

  LOCAL VARIABLES: None

  SHARED VARIABLES:
     uint8_t CS_pin: Read GPIO pin numbers
     uint16_t local_state: Overwritten with the new local_state (at most one bit different)

  GLOBAL VARIABLES: None

  DEPENDENCIES: SPI.h
  -----------------------------------------------------------------------------
*/
void NXP33996::turn_on(uint8_t id) {
  local_state |= (uint16_t)0x0001 << id;
  this->transfer(local_state);

  return;
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: turn_off() clears a bit in local_state and writes local_state to the device.

  OPERATION:   We first AND local_state with the inverse of 0x01 shifted left by id. This clears our target bit in local_state. We next call this->transfer and transfer the local_state

  ARGUMENTS: uint8_t id: which bit to set low

  RETURNS: NONE

  INPUTS:  NONE

  OUTPUTS: Data is sent over the SPI bus, the CS pin is brought low during the SPI operation

  LOCAL VARIABLES: None

  SHARED VARIABLES:
     uint8_t CS_pin: Read GPIO pin numbers
     uint16_t local_state: Overwritten with the new local_state (at most one bit different)

  GLOBAL VARIABLES: None

  DEPENDENCIES: SPI.h
  -----------------------------------------------------------------------------
*/
void NXP33996::turn_off(uint8_t id) {
  local_state &= ~((uint16_t)0x0001 << id);
  this->transfer(local_state);
  return;
}
