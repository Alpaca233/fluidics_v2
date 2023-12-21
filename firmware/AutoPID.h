/* AutoPID.h
   Fork of AutoPID
   https://github.com/r-downing/AutoPID

   This file implements two classes, AutoPID and AutoBangBang. AutoPID takes the setpoints, control type, PID parameters, and a floating point reading as inputs and gives a continuous variable control output. AutoBangBang does bang-bang control
   AutoPID Function Class Members:
     AutoPID: Constructor, initializes pointers to control variables and PID settings
     setGains: Set Kp, Ki, Kd
     setOutputRange: Set minimum, maximum output values
     setTimeStep: Set the amount of time between PID iterations
     run: Check if sufficient time has passed and run a PID iteration if so
     stop: Stop PID loop until begin() is called again
     begin: Enable the PID loop
     isStopped: return true if PID is stopped
     reset: Clear accumulated errors

  AutoBangBang Function Class Members:
    AutoBangBang: Constructor, intializes pointers to control variables and bang-bang settings
    setBangBang: Set BangBang params- upper and lower bounds for turning on/off 
    setOutputRange: Set what the output should be in the "on" and "off" states
    setTimeStep: Set time between bang-bang iterations
    run: Check if sufficient time has passed and run a bang-bang iteration if so
    stop: Stop until the next time begin() is called
    begin: enable the bang-bang control
    isStopped: return true if bang-bang is stopped


    Modifications:
    - Remove AutoPIDRelay (I will not be maintaining this feature)
    - Add documentation
    - Add integral wind-up limits
    - Add sign parameter (increased effort causes a more negative measurement)
    - Separate bang-bang control into a separate class

       Forked on: 11/13/2023
         Original Author: r-downing
         Contributor: Kevin Marx
*/

#ifndef AUTOPID_H
#define AUTOPID_H

#include <Arduino.h>

class AutoPID {
  public:
    AutoPID(double *input, double *setpoint, double *output, float sgn);
    void setGains(double Kp, double Ki, double Kd, double Ilim);
    void setOutputRange(double outputMin, double outputMax);
    void setTimeStep(uint32_t timeStep);
    void run();
    void begin();
    void stop();
    void reset();
    bool isStopped();
    double _integral, _previousError;
    
  private:
    float _sgn;
    double _Kp, _Ki, _Kd, _windingLimit;
    //double _integral, _previousError;
    double *_input, *_setpoint, *_output;
    double _outputMin, _outputMax;
    uint32_t _timeStep, _lastStep;
    bool _stopped, _gainsSet, _rangeSet, _timestepSet;
};//class AutoPID

class AutoBangBang {
  public:
    AutoBangBang(double *input, double *output, float sgn);
    void setThresholds(double threshLow, double threshHigh);
    void setOutputRange(double outputMin, double outputMax);
    void setTimeStep(uint32_t timeStep);
    void run();
    void begin();
    void stop();
    void reset();
    bool isStopped();
    
  private:
    float _sgn;
    double _threshLow, _threshHigh;
    double *_input, *_output;
    double _outputMin, _outputMax;
    uint32_t _timeStep, _lastStep;
    bool _stopped, _threshSet, _rangeSet, _timestepSet, _bbstate;
};//class AutoBangBang

#endif
