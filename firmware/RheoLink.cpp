/* RheoLink.h
   Define RheoLink Class
   https://www.idex-hs.com/docs/default-source/product-manuals/rheolink-i2c-communication-protocol-for-titanex.pdf.zip
   Control and IDEX selector valve using I2C

    Functions:
        RheoLink: Set up the class
            Arguments: uint8_t address
            Returns: None
        bool begin: Initialize the device. Return false if failed
            Arguments: TwoWire *w_
            Returns: If begun successfully, return true
        bool send_command: Send a command to the 
            Arguments: uint8_t pos - the new position
            Returns: Return true if successful
        uint8_t get_position: Get current position and error status
            Arguments: None
            Returns:
              99 – valve failure (valve can not be homed)
              88 – non-volatile memory error
              77 – valve configuration error or command mode error
              66 – valve positioning error
              55 – data integrity error
              44 – data CRC error
              3x – Problem connecting over I2C
                  31 – Data too long for buffer
                  32 – NACK on address tx
                  33 – NACK on data tx
                  34 – other error
                  35 – timeout
                  36 – other other error
              22 – Not initialized
              current valve position (1 to N) otherwise

       Created on: 8/10/2023
         Author: Kevin Marx
*/
#include "RheoLink.h"

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: RheoLink() initializes the selector valve class

  OPERATION:   None

  ARGUMENTS: None

  RETURNS: NONE

  INPUTS / OUTPUTS: NONE

  LOCAL VARIABLES: NONE

  SHARED VARIABLES: None

  GLOBAL VARIABLES: None

  DEPENDENCIES: None
  -----------------------------------------------------------------------------
*/
RheoLink::RheoLink()
{
  init_ = false;
  return;
}


/*
  -----------------------------------------------------------------------------
  DESCRIPTION: begin() initializes the I2C bus

  OPERATION:   We set the I2C address. The Wire library handles setting the low bit for read/write so we shift the address down a bit. Then, we store the I2C bus object pointer to a local variable

  ARGUMENTS:
      TwoWire *w:      Pointer to TwoWire object for I2C
      uint8_t address:      I2C write address of the pump

  RETURNS: 
      uint8_t err: I2C transmission error code

  INPUTS / OUTPUTS: NONE

  LOCAL VARIABLES: NONE

  SHARED VARIABLES:
     TwoWire *w_: pointer to stream object, written to and read from
     uint8_t address_: I2C address, written to and read from

  GLOBAL VARIABLES: None

  DEPENDENCIES: Wire.h
  -----------------------------------------------------------------------------
*/
uint8_t RheoLink::begin(TwoWire &w, uint8_t address) {

  address_ = address >> 1;
  
  w_ = &w;
  w_->begin();
  w_->beginTransmission(address_);

  init_ = true;

  return w_->endTransmission(address_);
}
/*
  -----------------------------------------------------------------------------
  DESCRIPTION: send_command() sends a command

  OPERATION:   We first initialize the checksum with the "write" address. We then send the command and data, updating the checksum. We then send the checksum and return with the I2C transmission error code.

  ARGUMENTS:
      uint8_t cmd: The command
      int8_t data: The data

  RETURNS:
      uint8_t err: The I2C error code.

  INPUTS / OUTPUTS: Data is sent over I2C.

  LOCAL VARIABLES:
      uint8_t checksum: Stores the checksum
      uint8_t err:      Stores the error value

  SHARED VARIABLES:
     TwoWire *w_: pointer to stream object

  GLOBAL VARIABLES: None

  DEPENDENCIES: Wire.h
  -----------------------------------------------------------------------------
*/
uint8_t RheoLink::send_command(RheoLinkCommand_t cmd, uint8_t data ) {
  uint8_t checksum = address_ << 1;
  uint8_t err;

  if (!init_){
    return 22;
  }
  
  w_->beginTransmission(address_);
  w_->write(cmd);
  checksum = checksum ^ cmd;
  w_->write(data);
  checksum = checksum ^ data;
  w_->write(checksum);

  err = w_->endTransmission(true);

  // there's a problem with the firmware on the selector valve - open and close a dummy transmission to terminate the command
  w_->beginTransmission(0);
  w_->endTransmission();
  
  return err;
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: read_register() reads a value from the selector valve.

  OPERATION:   We send the I2C command to command the register and return its value or an error code.

  ARGUMENTS: NONE

  RETURNS:
      uint8_t err: The value or error code.

  INPUTS / OUTPUTS: Data is sent over I2C.

  LOCAL VARIABLES:
      uint8_t err: Stores the error values

  SHARED VARIABLES:
     TwoWire *w_: pointer to stream object

  GLOBAL VARIABLES: None

  DEPENDENCIES: Wire.h
  -----------------------------------------------------------------------------
*/
uint8_t RheoLink::read_register(RheoLinkCommand_t target){
  if (!init_){
    return 22;
  }
  
  uint8_t err = this->send_command(target);

  // If there was a problem connecting, return an error
  if(err != 0){
    return 30 + err;
  }
  // Otherwise, request the data
  err = w_->requestFrom(address_, 3, true);
  // If we didn't get any data, return an error
  if(err == 0){
    return 36;
  }
  // Parse the data RXed - we only care about the first byte
  err =  w_->read();
  // Clear the buffer
  while(w_->available())
    w_->read();

  return err;
}


/*
  -----------------------------------------------------------------------------
  DESCRIPTION: block_until_done() blocks operation until the selector valve is done moving, then returns the error code.

  OPERATION:   We first record the initial time. Then, we read the the status register until we stop seeing a data read error or we time out. We then report the error.

  ARGUMENTS: NONE

  RETURNS:
      uint8_t err: The value or error code.

  INPUTS / OUTPUTS: Data is sent over I2C.

  LOCAL VARIABLES:
      uint8_t err: Stores the error values
      uint32_t t0: Stores the initial time

  SHARED VARIABLES:
     TwoWire *w_: pointer to stream object

  GLOBAL VARIABLES: None

  DEPENDENCIES: Wire.h
  -----------------------------------------------------------------------------
*/
uint8_t RheoLink::block_until_done(uint32_t timeout){
  if (!init_){
    return 22;
  }
  
  uint8_t err = this->read_register(RheoLink_STATUS);
  uint32_t t0 = millis();
  while((err < 40) and (err >=30) and ((millis() - t0) < timeout)){
    // If error is 30 - 39 AND we didn't time out yet, wait a bit and get the error again
    delay(5);
    err = this->read_register(RheoLink_STATUS);
  }
  return err;
}
