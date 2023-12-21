/*
    AutoPID.cpp
    This file contains classes for PID and bang-bang control

   AutoPID Class Members:
     AutoPID: Constructor, initializes pointers to control variables and PID settings
     setGains: Set Kp, Ki, Kd
     setOutputRange: Set minimum, maximum output values
     setTimeStep: Set the amount of time between PID iterations
     run: Check if sufficient time has passed and run a PID iteration if so
     stop: Stop PID loop until begin() is called again
     begin: Enable the PID loop
     isStopped: return true if PID is stopped
     reset: Clear accumulated errors
*/

#include "AutoPID.h"


/*
  -----------------------------------------------------------------------------
  DESCRIPTION: AutoPID() constructor initializes the pointers to the shared input, setpoint, and output variables. Also save the sign (i.e. whether increasing the output increases or decreases the measuremet)

  OPERATION:   Save the input, setpoint, and output pointers and save flags indicating the rest of the PID has not been initialized

  ARGUMENTS:
      double *input, *setpoint, *output: Pointers to the input, setpoint, and output variables
      float sgn: +1 or -1, indicates whether increasing output increases or decreases the measurement

  RETURNS: None

  INPUTS / OUTPUTS: None

  LOCAL VARIABLES: None

  SHARED VARIABLES:
      double _input, _setpoint, _output: Pointers are written, the variables pointed to are not written to or read from
      float _sgn: Written to
      bool _stopped, _gainsSet, _rangeSet, _timestepSet: Written to

  GLOBAL VARIABLES: None

  DEPENDENCIES: Arduino.h
  -----------------------------------------------------------------------------
*/
AutoPID::AutoPID(double *input, double *setpoint, double *output, float sgn) {
  _input = input;
  _setpoint = setpoint;
  _output = output;
  _sgn = sgn / abs(sgn);

  _stopped = true; // Initially stopped

  // Values are not yet initialized!
  _gainsSet = false;
  _rangeSet = false;
  _timestepSet = false;

}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: setGains() sets the Kp, Ki, Kd gains and integral winding limit to shared variables

  OPERATION:   Save the Kp, Ki, Kd, integral winding limit and set a flag indicating that the gains have been set

  ARGUMENTS:
      double Kp, Ki, Kd: PID gains

  RETURNS: None

  INPUTS / OUTPUTS: None

  LOCAL VARIABLES: None

  SHARED VARIABLES:
      double _Kp, _Ki, _Kd, _windingLimit: Written to
      bool _gainsSet: Written to

  GLOBAL VARIABLES: None

  DEPENDENCIES: None
  -----------------------------------------------------------------------------
*/
void AutoPID::setGains(double Kp, double Ki, double Kd, double Ilim) {
  _Kp = Kp;
  _Ki = Ki;
  _Kd = Kd;
  _windingLimit = Ilim;

  _gainsSet = true;

  return;
}


/*
  -----------------------------------------------------------------------------
  DESCRIPTION: setTimeStep() sets the timestep in units ms to a shared variable

  OPERATION:   Save the timestep and set a flag indicating that the timestep has been set

  ARGUMENTS:
      uint32_t timeStep: Time step in milliseconds

  RETURNS: None

  INPUTS / OUTPUTS: None

  LOCAL VARIABLES: None

  SHARED VARIABLES:
      uint32_t _timeStep: Written to
      bool _timestepSet: Written to

  GLOBAL VARIABLES: None

  DEPENDENCIES: None
  -----------------------------------------------------------------------------
*/
void AutoPID::setTimeStep(uint32_t timeStep) {
  _timeStep = timeStep;

  _timestepSet = true;

  return;
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: setOutputRange() sets the minimum and maximum output values

  OPERATION:   Save the min, max values and set a flag indicating that the bounds have been set

  ARGUMENTS:
      double outputMin, outputMax: min and max possible output values

  RETURNS: None

  INPUTS / OUTPUTS: None

  LOCAL VARIABLES: None

  SHARED VARIABLES:
      double _outputMin, _outputMax: Written to
      bool _rangeSet: Written to

  GLOBAL VARIABLES: None

  DEPENDENCIES: None
  -----------------------------------------------------------------------------
*/
void AutoPID::setOutputRange(double outputMin, double outputMax) {
  _outputMin = outputMin;
  _outputMax = outputMax;

  _rangeSet = true;

  return;
}


void AutoPID::begin() {
  _stopped = false;
  this->reset();
}
void AutoPID::stop() {
  _stopped = true;
  this->reset();
}
void AutoPID::reset() {
  _lastStep = millis();
  _integral = 0;
  _previousError = 0;
}
bool AutoPID::isStopped() {
  return _stopped;
}


/*
  -----------------------------------------------------------------------------
  DESCRIPTION: run() should be called every main loop cycle and updates the output shared variable using the PID parameters.

  OPERATION:   First, check if stopped. If so, return out. If the PID control has not been fully initialized, also return out. Similarly, if not enough time has passed since the last timestep, return out. Otherwise, use the PID parameters, measurement, and setpoint to set a new output.

  ARGUMENTS: None

  RETURNS: None

  INPUTS / OUTPUTS: None

  LOCAL VARIABLES:
    uint32_t _dT: Time in ms since last iteration
    double _dTseconds: Time elapsed since last iteration in seconds
    double _error: Difference between setpoint and measurement
    double _dError: Differential error
    double _PID: PID output (before constrain)

  SHARED VARIABLES:
    double _Kp, _Ki, _Kd, _outputMin, _outputMax, _windingLimit: Read from
    bool _stopped, _gainsSet, _rangeSet, _timestepSet: Read from
    dobule _integral, _previousError: Read from and written to
    uint32_t _lastStep: Read from and written to

    double *_input, *_setpoint: Read from the variables pointed to
    double *_output: Write to the variable pointed to

  GLOBAL VARIABLES: None

  DEPENDENCIES: None
  -----------------------------------------------------------------------------
*/
void AutoPID::run() {
  uint32_t _dT;
  double _error, _dError, _dTseconds, _PID;
  // If stopped, don't do anything
  if (_stopped) {
    return;
  }
  // If not fully initialized, don't do anything
  if (!_gainsSet || !_rangeSet || !_timestepSet) {
    return;
  }
  // Get time since last run
  _dT = millis() - _lastStep;
  // If insufficient time has passed, don't do anything
  if (_dT < _timeStep) {
    return;
  }
  // Convert from ms to s
  _dTseconds = _dT / 1000.0;

  // Otherwise, we are ready to perform the PID calculation!
  _lastStep = millis();
  _error = *_setpoint - (*_input * _sgn);

  _integral += ((_error + _previousError) / 2.0) * _dTseconds;   // Riemann sum integral with filtering
  _integral = constrain(_integral, -UINT16_MAX, UINT16_MAX); // Enforce wind-up limit

  _dError = (_error - _previousError) / _dTseconds;            // Differential error
  _previousError = _error;

  _PID = (_Kp * _error) + (_Ki * _integral) + (_Kd * _dError);

  _PID = constrain(_PID, _outputMin, _outputMax);
  *_output = _PID;

  return;
}

/*----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------*/


/*
  -----------------------------------------------------------------------------
  DESCRIPTION: AutoBangBang() constructor initializes the pointers to the shared input and output variables. Also save the sign (i.e. whether increasing the output increases or decreases the measuremet)

  OPERATION:   Save the input and output pointers and save flags indicating the rest of the bang-bang controller has not been initialized

  ARGUMENTS:
      double *input, *output: Pointers to the input and output variables
      float sgn: +1 or -1, indicates whether increasing output increases or decreases the measurement

  RETURNS: None

  INPUTS / OUTPUTS: None

  LOCAL VARIABLES: None

  SHARED VARIABLES:
      double _input, _output: Pointers are written, the variables pointed to are not written to or read from
      float _sgn: Written to
      bool _stopped, _gainsSet, _rangeSet, _timestepSet: Written to

  GLOBAL VARIABLES: None

  DEPENDENCIES: Arduino.h
  -----------------------------------------------------------------------------
*/
AutoBangBang::AutoBangBang(double *input, double *output, float sgn) {
  _input = input;
  _output = output;
  _sgn = sgn / abs(sgn);

  _stopped = true; // Initially stopped
  _bbstate = false;

  // Values are not yet initialized!
  _threshSet = false;
  _rangeSet = false;
  _timestepSet = false;

}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: setThresholds() sets the lower and upper thresholds for bang-bang control.

  OPERATION:   Save the lower and upper thresholds and set a flag indicating that the gains have been set. We do not check whether threshLow is lower than threshHigh

  ARGUMENTS:
      double threshLow, threshHigh: PID gains

  RETURNS: None

  INPUTS / OUTPUTS: None

  LOCAL VARIABLES: None

  SHARED VARIABLES:
      double _threshLow, _threshHigh: Written to
      bool _threshSet: Written to

  GLOBAL VARIABLES: None

  DEPENDENCIES: None
  -----------------------------------------------------------------------------
*/
void AutoBangBang::setThresholds(double threshLow, double threshHigh) {
  _threshLow = threshLow;
  _threshHigh = threshHigh;

  _threshSet = true;

  return;
}


/*
  -----------------------------------------------------------------------------
  DESCRIPTION: setTimeStep() sets the timestep in units ms to a shared variable

  OPERATION:   Save the timestep and set a flag indicating that the timestep has been set

  ARGUMENTS:
      uint32_t timeStep: Time step in milliseconds

  RETURNS: None

  INPUTS / OUTPUTS: None

  LOCAL VARIABLES: None

  SHARED VARIABLES:
      uint32_t _timeStep: Written to
      bool _timestepSet: Written to

  GLOBAL VARIABLES: None

  DEPENDENCIES: None
  -----------------------------------------------------------------------------
*/
void AutoBangBang::setTimeStep(uint32_t timeStep) {
  _timeStep = timeStep;

  _timestepSet = true;

  return;
}

/*
  -----------------------------------------------------------------------------
  DESCRIPTION: setOutputRange() sets the minimum and maximum output values

  OPERATION:   Save the min, max values and set a flag indicating that the bounds have been set

  ARGUMENTS:
      double outputMin, outputMax: min and max possible output values

  RETURNS: None

  INPUTS / OUTPUTS: None

  LOCAL VARIABLES: None

  SHARED VARIABLES:
      double _outputMin, _outputMax: Written to
      bool _rangeSet: Written to

  GLOBAL VARIABLES: None

  DEPENDENCIES: None
  -----------------------------------------------------------------------------
*/
void AutoBangBang::setOutputRange(double outputMin, double outputMax) {
  _outputMin = outputMin;
  _outputMax = outputMax;

  _rangeSet = true;

  return;
}


void AutoBangBang::begin() {
  _stopped = false;
  this->reset();
}
void AutoBangBang::stop() {
  _stopped = true;
  this->reset();
}
void AutoBangBang::reset() {
  _lastStep = millis();
}
bool AutoBangBang::isStopped() {
  return _stopped;
}


/*
  -----------------------------------------------------------------------------
  DESCRIPTION: run() should be called every main loop cycle and updates the output shared variable using the bang-bang parameters.

  OPERATION:   First, check if stopped. If so, return out. If the bang-bang control has not been fully initialized, also return out. Similarly, if not enough time has passed since the last timestep, return out. Otherwise, use the bang-bang parameters and measurement to set a new output.

  ARGUMENTS: None

  RETURNS: None

  INPUTS / OUTPUTS: None

  LOCAL VARIABLES:
    uint32_t _dT: Time in ms since last iteration

  SHARED VARIABLES:
    double _threshLow, _threshHigh, _outputMin, _outputMax: Read from
    bool _stopped, _threshSet, _rangeSet, _timestepSet: Read from
    uint32_t _lastStep: Read from and written to
    float _sgn: Read from
    bool _bbstate: current bang-bang state

    double *_input: Read from the variables pointed to
    double *_output: Write to the variable pointed to

  GLOBAL VARIABLES: None

  DEPENDENCIES: None
  -----------------------------------------------------------------------------
*/
void AutoBangBang::run() {
  uint32_t _dT;
  double corrected_input = *_input * _sgn;

  // If stopped, don't do anything
  if (_stopped) {
    return;
  }
  // If not fully initialized, don't do anything
  if (!_threshSet || !_rangeSet || !_timestepSet) {
    return;
  }
  // Get time since last run
  _dT = millis() - _lastStep;
  // If insufficient time has passed, don't do anything
  if (_dT < _timeStep) {
    return;
  }

  // Otherwise, we are ready to perform the bang-bang calculation!
  _lastStep = millis();
  // get the new state - turn off if too high
  if (corrected_input >= _threshHigh) {
    _bbstate = false;
  }
  // turn on if too low
  else if (corrected_input <= _threshLow) {
    _bbstate = true;
  }

  *_output = _bbstate ? _outputMax : _outputMin;

  return;
}
