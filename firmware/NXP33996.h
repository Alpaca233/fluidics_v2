/* NXP33996.h
 * Define NXP33996 Class
 * https://www.nxp.com/products/power-management/smart-switches-and-drivers/low-side-switches/16-output-switch-with-spi-control:MC33996
 * 16-Output Switch with SPI Control
 * 
 * This class implements the folowing features:
 *      - Initialization
 *      - Write arbitrary 16 bits to the outputs
 *      - Set select bit
 *      - Clear select bit
 *      - Clear all bits
 *      - Get current state
 * 
 * Class Members: 
 *  Variables:
 *      uint8_t CS_pin, PWM_pin, RST_pin: GPIO pins for chip select (active low), PWM control, and reset respectively
 *      uint16_t local_state: state of all 16 outputs
 *  Functions:
 *      NXP33996: set the private variables
 *      bool begin: set CS, PWM, RST pins as outputs and initializes SPI, return false if failed
 *      uint16_t transfer: overwrite all 16 outputs with uint16_t id and return the previous state
 *      void clear_all: reset all 16 outputs
 *      void turn_on: set specific single output without modifying the others
 *      void turn_off: reset specific single output without modifying others
 *      uint16_t get_state: get the current state
 * 
 *     Created on: 9/13/2022
 *       Author: Kevin Marx
*/

#ifndef NXP33996_H_
#define NXP33996_H_

#include "Arduino.h"
#include <SPI.h>

// Define constants for commands
#define ON_OFF_CTRL 0x00

// Define the class
class NXP33996{
    private:
        uint8_t   CS_pin;
        uint8_t   PWM_pin;
        uint8_t   RST_pin;
        SPIClass *s_;
        SPISettings spiSettings_;
        bool init_;
    public:
        NXP33996();
        bool begin(uint8_t cs_pin, uint8_t pwm_pin, uint8_t rst_pin, SPIClass  &s);
        uint16_t transfer(uint16_t id);
        void clear_all();
        void turn_on(uint8_t id);
        void turn_off(uint8_t id);
        uint16_t  local_state;
};

#endif /* NXP33996_H_ */
