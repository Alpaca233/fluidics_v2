/* OPX350.h
   Define OPX350 Class
   https://www.ttelectronics.com/TTElectronics/media/ProductFiles/Datasheet/OPB350.pdf
   Fluid/Air Sensor

   This class implements the folowing features:
        - Initialization
        - Calibrate sensor
        - Read bits from sensor

   Class Members:
    Variables:
        uint8_t LOW_A_pin_, HIGH_B_pin_, CALIB_pin_: GPIO pins for reading from and calibrating the sensor
    Functions:
        OPX350: set the private variables
        bool begin: set pin numbers, set CALIB_pin_ as output, LOW_A_pin_ and HIGH_B_pin_ as inputs. Always returns true
        bool calibrate: Send a pulse on the CALIB_pin_ and wait for the calibration to finish or until timeout. This is a blocking function.
        uint8_t read: Return the reading on HIGH_B_pin_ on bit 1 and LOW_A_pin_ on bit 0.

       Created on: 9/13/2022
         Author: Kevin Marx
*/

#ifndef OPX350_H_
#define OPX350_H_

#include <stddef.h>
#include <stdint.h>
#include <Arduino.h>

// Constants for operation
#define OPX35_CALIB_LOW_PULSE_MS 100
#define OPX35_CALIB_TIMEOUT_MS   3000

enum OPX350_READINGS {
  OPX350_LOW   = 0b001,
  OPX350_HIGH  = 0b010,
  OPX350_ERR   = 0b100,
  OPX350_RD_ER = 0b011,
  OPX350_NONE  = 0b000
};


// Class definition
class OPX350 {
  public:
    OPX350();
    bool begin(uint8_t LOW_A_pin, uint8_t HIGH_B_pin, uint8_t CALIB_pin);
    bool calibrate();
    OPX350_READINGS read();
  private:
    uint8_t LOW_A_pin_;
    uint8_t HIGH_B_pin_;
    uint8_t CALIB_pin_;
    bool    init_;
};

#endif /* OPX350_H_ */
