/*
    TTP.cpp
    This file contains functions for initializing and controlling the disc pump

    bool TTP_init: Initialize the disc pump's power limit, signal source, mode, and whether it should stream data. Returns true if successful.
      Arguments: HardwareSerial &S,  int16_t pwr_lim, uint8_t src, uint8_t mode, uint8_t stream
    bool TTP_enable: Enable/disable the disc pump. Returns true if successful.
      Arguments: HardwareSerial &S, bool en
    bool TTP_set_pwr_limit: change the power limit of the disc pump.
       Arguments: HardwareSerial &S, int16_t pwr_lim
    bool TTP_set_target:  Set the pump's setpoint. Returns true if successful.
      Arguments: HardwareSerial &S, float target
    bool TTP_get_status:  Get error codes, drive frequency, drive power, drive current, drive voltage, and the power limit and saves them to shared variables. Returns true if successful.
      Arguments: HardwareSerial &S, uint16_t &error_code, int16_t &drive_freq, float &dive_pwr, float &drive_current, float &drive_voltage, float &power_limit
    int16_t TTP_read_int: Read an integer from a register in the disc pump
      Arguments: HardwareSerial &S, uint8_t reg
    float TTP_read_float: Read a float from a register in the disc pump
      Arguments: HardwareSerial &S, uint8_t reg

    bool TTP_send_packet: Send the write buffer to the pump and populate the read the response into the read buffer. Also write the index on the response pointer showing when the pump's response begins
      Arguments: HardwareSerial &S, char *tx_buffer, char *rx_buffer, uint16_t &cmd_ptr
    bool TTP_write_register: Write a value to a register and return true if it was successfull. This function is overloaded
      Arguments: HardwareSerial &S, int16_t dat
      Arguments: HardwareSerial &S, float dat

*/
#include "TTP.h"

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: TTP() initializes the disc pump class

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
TTP::TTP() {
  init_ = false;
  return;
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: begin() stores the HardwareSerial object to a shared variable

  OPERATION:   We store the argument to a shared variable.

  ARGUMENTS:
      HardwareSerial &s:      Pointer to HardwareSerial object for serial

  RETURNS: true

  INPUTS / OUTPUTS: NONE

  LOCAL VARIABLES: NONE

  SHARED VARIABLES:
     HardwareSerial *s_: pointer to stream object, written to and read from

  GLOBAL VARIABLES: None

  DEPENDENCIES: Arduino.h
  -----------------------------------------------------------------------------
*/
bool TTP::begin(HardwareSerial &s) {
  s_ = &s;
  return true;
}
/*
  -----------------------------------------------------------------------------
  DESCRIPTION: send_packet() sends a byte stream to the disc pump and reads the response back into a shared array.

  OPERATION: We write the full contents of the tx_buffer to the pump over serial and wait for a response. We then store the response to the rx_buffer and make sure the response was echoed properly. If the response times out or is not echoed properly, we try sending the message again. We try up to TTP_N_TRIES times.

  ARGUMENTS:
      char *tx_buffer:   pointer to array containing characters to send. This buffer is not changed
      char *rx_buffer:   pointer to array containing recieved characters. This buffer is overwritten

  RETURNS:
      bool success:     Returns true if the read/write worked properly

  INPUTS / OUTPUTS: The Serial lines are used as inputs and outputs to transmit data

  LOCAL VARIABLES:
      uint16_t rx_ptr: keep track of index in rx_buffer
      uint32_t time_0: track time for timeout
      uint16_t cmd_ptr: track length of tx

  SHARED VARIABLES:
      HardwareSerial *s_: pointer to stream object, written to and read from
      char *tx_buffer:   array with characters to send, not modified
      char *rx_buffer:   array with received characters, overwritten

  GLOBAL VARIABLES: None

  DEPENDENCIES: Arduino.h
  -----------------------------------------------------------------------------
*/
bool TTP::send_packet(char *tx_buffer, char *rx_buffer) {
  uint16_t rx_ptr;
  uint32_t time_0;
  if(!init_){
    return false;
  }

  // Get the length of the message to send - should be less than 32 bytes
  uint16_t cmd_ptr = strlen(tx_buffer);
  cmd_ptr = min(cmd_ptr, TTP_BUFFER_SIZE);

  for (uint8_t i = 0; i < TTP_N_TRIES; i++) { // try writing multiple times
    rx_ptr = 0; // reset the rx pointer
    memset(rx_buffer, 0, TTP_BUFFER_SIZE); // reset the read buffer
    s_->clear(); // clear stream's RX buffer
    s_->print(tx_buffer);
    s_->flush(); // Wait for any transmitted data still in buffers to actually transmit

    // wait for a response
    time_0 = millis();
    while (!s_->available() && ((millis() - time_0) < TTP_READ_TIMEOUT_mS)) {
      delayMicroseconds(TTP_IDLETIME_uS);
    }
    // wait for a response
    // if we have a response, process it. otherwise, fall through to the next for loop
    if (s_->available()) {
      // read every byte into the buffer
      while (s_->available()) {
        rx_buffer[rx_ptr++] = s_->read();
        delayMicroseconds(TTP_IDLETIME_uS);
      }
      // We are expecting the response to echo the request and have additional data if we are reading from one of the pump's registers
      // If expectation met, return out. Otherwise, loop again
      if ((cmd_ptr <= rx_ptr) && (strncmp(tx_buffer, rx_buffer, (cmd_ptr-1)) == 0)) {
        return true;
      }
    }
  }
  return false; // not receiving the sent command within 1 ms for 3 attempts
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: read_int() requests data from a register and returns the data as an int

  OPERATION: We format the register number into a UART request to the disc pump. If we get a valid result, return it. Otherwise, return an error.

  ARGUMENTS:
      HardwareSerial &S:  stream class to read from Serial, Serial1, etc.
      uint8_t reg:        register to read from

  RETURNS:
      int16_t val:        Returns the value if the read worked properly and TTP_INT_READ_ERR (INT16_MIN) otherwise

  INPUTS / OUTPUTS: The Serial lines are used as inputs and outputs to transmit data

  LOCAL VARIABLES:
      char rx[], tx[]: Null-terminated character arrays for sending, receiving data
      bool is_valid:   track whether the command sent was valid
      uint16_t cmd_len: track length of the command sent so data can be read back

  SHARED VARIABLES:
      HardwareSerial *s_: pointer to stream object, written to and read from

  GLOBAL VARIABLES: None

  DEPENDENCIES: Arduino.h
  -----------------------------------------------------------------------------
*/
int16_t TTP::read_int(TTPRegisterMap_t reg) {
  char rx[TTP_BUFFER_SIZE];
  char tx[TTP_BUFFER_SIZE];
  bool is_valid;
  int16_t cmd_len;

  if(!init_){
    return false;
  }

  // Format the UART command and get its length
  cmd_len = sprintf(tx, TTP_READ_REG_FORMAT, reg);
  // If the sprintf failed, return error
  if ((cmd_len < 0) || (cmd_len > TTP_BUFFER_SIZE)) {
    return TTP_INT_READ_ERR;
  }
  // Send the command
  is_valid = this->send_packet(tx, rx);

  // Read the response
  if (is_valid) {
    // rx has the command echoed and a comma before the returned int; index past those to get to the int
    return atoi(&rx[cmd_len + 1]);
  }
  else {
    return TTP_INT_READ_ERR;
  }
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: read_float() requests data from a register and returns the data as a float

  OPERATION: We format the register number into a UART request to the disc pump. If we get a valid result, return it. Otherwise, return an error.

  ARGUMENTS:
      HardwareSerial &S:  stream class to read from Serial, Serial1, etc.
      uint8_t reg:        register to read from

  RETURNS:
      int16_t val:        Returns the value if the read worked properly and TTP_FLT_READ_ERR (FLT_MAX) otherwise

  INPUTS / OUTPUTS: The Serial lines are used as inputs and outputs to transmit data

  LOCAL VARIABLES:
      char rx[], tx[]: Null-terminated character arrays for sending, receiving data
      bool is_valid:   track whether the command sent was valid
      uint16_t cmd_len: track length of the command sent so data can be read back

  SHARED VARIABLES:
      HardwareSerial *s_: pointer to stream object, written to and read from

  GLOBAL VARIABLES: None

  DEPENDENCIES: Arduino.h
  -----------------------------------------------------------------------------
*/
float TTP::read_float(TTPRegisterMap_t reg) {
  char rx[TTP_BUFFER_SIZE];
  char tx[TTP_BUFFER_SIZE];
  bool is_valid;
  int16_t cmd_len;

  if(!init_){
    return false;
  }

  // Format the UART command and get its length
  cmd_len = sprintf(tx, TTP_READ_REG_FORMAT, reg);
  // If the sprintf failed, return error
  if ((cmd_len < 0) || (cmd_len > TTP_BUFFER_SIZE)) {
    return TTP_INT_READ_ERR;
  }
  // Send the command
  is_valid = this->send_packet(tx, rx);

  // Read the response
  if (is_valid) {
    // rx has the command echoed and a comma before the returned int; index past those to get to the int
    return atof(&rx[cmd_len + 1]);
  }
  else {
    return TTP_FLT_READ_ERR;
  }
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: write_register() writes either an int or a float to a register in the disc pump. This function is overloaded so it can take either an int or float as an argument

  OPERATION: We format the register number and int/float into a UART request to the disc pump. If we get a valid echo, return true.

  ARGUMENTS:
      TTPRegisterMap_t reg:  register to read from
      int16_t/float dat:     data to write

  RETURNS:
      bool valid:         Returns true if the write succeeded

  INPUTS / OUTPUTS: The Serial lines are used as inputs and outputs to transmit data

  LOCAL VARIABLES: None

  SHARED VARIABLES:
      HardwareSerial *s_: pointer to stream object, written to and read from

  GLOBAL VARIABLES: None

  DEPENDENCIES: Arduino.h
  -----------------------------------------------------------------------------
*/
bool TTP::write_register(TTPRegisterMap_t reg, int16_t dat) {
  char rx[TTP_BUFFER_SIZE];
  char tx[TTP_BUFFER_SIZE];
  int16_t cmd_len;

  if(!init_){
    return false;
  }

  // Format the UART command
  cmd_len = sprintf(tx, TTP_WR_REG_INT_FORMAT, reg, dat);
  // return with error if sprintf failed
  if ((cmd_len < 0) || (cmd_len > TTP_BUFFER_SIZE)) {
    return false;
  }
  // Send the command
  return this->send_packet(tx, rx);
}
bool TTP::write_register(TTPRegisterMap_t reg, uint16_t dat) {
  char rx[TTP_BUFFER_SIZE];
  char tx[TTP_BUFFER_SIZE];
  int16_t cmd_len;

  if(!init_){
    return false;
  }

  // Format the UART command
  cmd_len = sprintf(tx, TTP_WR_REG_INT_FORMAT, reg, dat);
  // return with error if sprintf failed
  if ((cmd_len < 0) || (cmd_len > TTP_BUFFER_SIZE)) {
    return false;
  }
  // Send the command
  return this->send_packet(tx, rx);
}
bool TTP::write_register(TTPRegisterMap_t reg, float dat) {
  char rx[TTP_BUFFER_SIZE];
  char tx[TTP_BUFFER_SIZE];
  int16_t cmd_len;

  // Format the UART command
  cmd_len = sprintf(tx, TTP_WR_REG_FLT_FORMAT, reg, dat);
  // return with error if sprintf failed
  if ((cmd_len < 0) || (cmd_len > TTP_BUFFER_SIZE)) {
    return false;
  }
  // Send the command
  return this->send_packet(tx, rx);
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: init() initializes the disc pump with the power limit, source, mode, and stream settings.

  OPERATION: We first constrain the power limit to be betweeen the min and max values. Then, we write the power limit, setpoint source, operation mode, and stream mode to the registers in this order. If all the writes are successful, return true.

  ARGUMENTS:
      int16_t pwr_lim:   Power limit in units milliwatts
      uint8_t src:       Flag indicating what the setpoint source should be, sent over serial, from a sensor, or from one of the analog pins
      uint8_t mode:      Flag indicating mode, manual, PID, or bang-bang
      uint8_t stream:    Flag indicating whether the pump controller should stream data

  RETURNS:
      bool pump_connected:     return true if initialization was successful

  INPUTS / OUTPUTS: The Serial lines are used as inputs and outputs to transmit data

  LOCAL VARIABLES: None

  SHARED VARIABLES:
      HardwareSerial *s_: pointer to stream object, written to and read from

  GLOBAL VARIABLES: None

  DEPENDENCIES: Arduino.h
  -----------------------------------------------------------------------------
*/

bool TTP::init(int16_t pwr_lim, uint8_t src, uint8_t mode, uint8_t stream) {
  int16_t time_0;
  bool success = true;
  pwr = 0;

  s_->begin(TTP_BAUDRATE);

  // wait for the serial port to open
  time_0 = millis();
  while ((!s_->available()) && ((millis() - time_0) < TTP_READ_TIMEOUT_mS)) {
    delayMicroseconds(TTP_IDLETIME_uS);
  }
  // time out
  if ((millis() - time_0) > TTP_READ_TIMEOUT_mS) {
    success = false;
  }

  pwr_lim = constrain(pwr_lim, TTP_MIN_PWR, TTP_MAX_PWR);

  // success is true only if all writes succeed
  success = this->write_register(TTP_PWR_LIMIT, (int16_t)pwr_lim)  && success;
  success = this->write_register(TTP_CTRL_MODE, (int16_t)mode)     && success;
  success = this->write_register(TTP_MANUAL_SRC, (int16_t)src)     && success;
  success = this->write_register(TTP_STREAM_MODE, (int16_t)stream) && success;
  init_ = true;
  return success;
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: enable() enables/disables the disc pump

  OPERATION:  We write to the enable register and return true if the write was successful

  ARGUMENTS:
      bool en: Set true to enable, false to disable

  RETURNS:
      bool success:     return true if write was successful

  INPUTS / OUTPUTS: The Serial lines are used as inputs and outputs to transmit data

  LOCAL VARIABLES: None

  SHARED VARIABLES: None

  GLOBAL VARIABLES: None

  DEPENDENCIES: None
  -----------------------------------------------------------------------------
*/

bool TTP::enable(bool en) {
  if(!init_){
    return false;
  }
  return this->write_register(TTP_ENABLED, (int16_t)en);
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: set_pwr_limit() sets the pump's power limit.

  OPERATION:  We first constrian the power limit to be between the min and max value, then we write to the power limit register and return true if the write was successful

  ARGUMENTS:
      int16_t pwr_lim:   Power limit in units milliwatts

  RETURNS:
      bool success:     return true if write was successful

  INPUTS / OUTPUTS: The Serial lines are used as inputs and outputs to transmit data

  LOCAL VARIABLES: None

  SHARED VARIABLES: None

  GLOBAL VARIABLES: None

  DEPENDENCIES: None
  -----------------------------------------------------------------------------
*/
bool TTP::set_pwr_limit(uint16_t pwr_lim) {
  if(!init_){
    return false;
  }
  
  pwr_lim = constrain(pwr_lim, TTP_MIN_PWR, TTP_MAX_PWR);
  return this->write_register(TTP_PWR_LIMIT, pwr_lim);
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: set_target() sets the pump's target(open loop) power.

  OPERATION:  We first constrian the power to be between the min and max value, then we write to the setpoint register and return true if the write was successful

  ARGUMENTS:
      HardwareSerial &S: stream class to read from Serial, Serial1, etc.
      float target:      Output power in units milliwatts

  RETURNS:
      bool success:     return true if write was successful

  INPUTS / OUTPUTS: The Serial lines are used as inputs and outputs to transmit data

  LOCAL VARIABLES:
      bool success

  SHARED VARIABLES:
      float pwr: Track power

  GLOBAL VARIABLES: None

  DEPENDENCIES: None
  -----------------------------------------------------------------------------
*/
bool TTP::set_target(float target) {
  bool success;
  if(!init_){
    return false;
  }

  target = constrain(target, TTP_MIN_PWR, TTP_MAX_PWR);
  success = this->write_register(TTP_SET_VALUE, target);
  if (success) {
    pwr = target;
  }

  return success;
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: get_status() overwrites shared variables with the disc pump's error code register, drive frequency, drive power, drive current, drive voltage, and power limit. We return false of any readings failed.

  OPERATION:  We read the data from the registers into our shared variables. Then, if any of the shared variables have an error value, return false

  ARGUMENTS:
      uint16_t &error_code, int16_t &drive_freq, float &dive_pwr, float &drive_current, float &drive_voltage, float &power_limit

  RETURNS:
      bool success:     return true if write was successful

  INPUTS / OUTPUTS: The Serial lines are used as inputs and outputs to transmit data

  LOCAL VARIABLES: None

  SHARED VARIABLES:
      uint16_t &error_code, int16_t &drive_freq, float &drive_pwr, float &drive_current, float &drive_voltage, float &power_limit

  GLOBAL VARIABLES: None

  DEPENDENCIES: None
  -----------------------------------------------------------------------------
*/
bool TTP::get_status(int16_t &error_code, int16_t &drive_freq, float &drive_pwr, float &drive_current, float &drive_voltage, float &power_limit) {
  bool success = true;
  if(!init_){
    return false;
  }

  error_code     = this->read_int(TTP_ERR_CODE);
  success = success & (error_code != TTP_INT_READ_ERR); // set success false if we fail to read
  drive_freq     = this->read_int(TTP_DRV_FREQ);
  success = success & (error_code != TTP_INT_READ_ERR);
  drive_pwr      = this->read_float(TTP_DRV_PWR);
  success = success & (error_code != TTP_FLT_READ_ERR);
  drive_pwr      = this->read_float(TTP_DRV_PWR);
  success = success & (error_code != TTP_FLT_READ_ERR);
  drive_current  = this->read_float(TTP_DRV_CURRENT);
  success = success & (error_code != TTP_FLT_READ_ERR);
  drive_voltage  = this->read_float(TTP_DRV_VOLT);
  success = success & (error_code != TTP_FLT_READ_ERR);
  power_limit    = this->read_float(TTP_PWR_LIMIT);
  success = success & (error_code != TTP_FLT_READ_ERR);

  return success;
}
