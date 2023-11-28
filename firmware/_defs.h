
#define FROM_MCU_MSG_LENGTH 30
#define TX_INTERVAL_MS 60

#define VOLUME_UL_MAX 5000

#define KP_MAX   128
#define KI_MAX   128
#define KD_MAX   128
#define ILIM_MAX UINT32_MAX

#define VALVES_RST 10
#define VALVES_CS   2
#define VALVES_PWM  3
#define VALVES_SPI     SPI

#define FLUIDSENSORFRONT_A 27
#define FLUIDSENSORFRONT_B 26
#define FLUIDSENSORFRONT_C 31

#define FLUIDSENSORBACK_A  28
#define FLUIDSENSORBACK_B  28
#define FLUIDSENSORBACK_C  30

#define SELECTORVALVE_WIRE Wire
#define SELECTORVALVE_QTY  2     // Only 2 are actually installed here
#define SELECTORVALVE_MAX  5     // Support up to 5 valves  
const uint8_t SELECTORVALVE_ADDRS[] = {0x1E, 0x0E, 0x00, 0x00, 0x00}; // 0x00 is dummy address

#define SLF3X_WIRE0   Wire
#define SLF3X_WIRE1   Wire1
#define SLF3X_WIRE2   Wire2
#define PERFORM_CRC  true

#define SSCX_SPI     SPI
#define SSCX_QTY      2 // Only 2 are installed here
#define SSCX_MAX      4 // Support up to 4 pressure sensors
const uint8_t PRESSURE_CS[] = {37, 36, 35, 34}; // Only index 0 and 1 are populated on most boards

#define TTP_UART             Serial3
#define TTP_SELECTED_MODE    TTP_MODE_MANUAL
#define TTP_SELECTED_STREAM  TTP_STREAM_DISABLE
#define TTP_SELECTED_SRC     TTP_SRC_SETVAL
#define TTP_PWR_LIM_mW       TTP_MAX_PWR
#define DISCPUMP_PWR_mW_GO    100

#define TX_INTERVAL_MS 100

enum InternalState_t {
  INTERNAL_STATE_IDLE = 0,
  INTERNAL_STATE_INITIALIZING_MEDIUM = 1,
  INTERNAL_STATE_LOADING_MEDIUM      = 2,
  INTERNAL_STATE_VENT_VB0            = 3,
  INTERNAL_STATE_UNLOADING           = 4,
  INTERNAL_STATE_CLEARING            = 5
};

enum CommandExecution_t {
  COMPLETED_WITHOUT_ERRORS  = 0,
  IN_PROGRESS               = 1,
  CMD_INVALID               = 2,
  CMD_EXECUTION_ERROR       = 3
};

enum SerialCommands_t {
  CLEAR                        = 0,
  INITIALIZE_DISC_PUMP         = 1,
  INITIALIZE_PRESSURE_SENSOR   = 2,
  INITIALIZE_FLOW_SENSOR       = 3,
  INITIALIZE_BUBBLE_SENSORS    = 4,
  INITIALIZE_VALVES            = 5,
  INITIALIZE_BANG_BANG_PARAMS  = 6,
  INITIALIZE_PID_PARAMS        = 7,
//  PRETEST_PRESSURE_START 6
//  PRETEST_VACUUM_START 7
//  LOAD_MEDIUM_START 8
//  UNLOAD_MEDIUM_START 9
//  CLEAR_MEDIUM_START 10
//  SET_SOLENOID_VALVES   11
//  LOAD_MEDIUM_VOLUME_START 12
//  UNLOAD_MEDIUM_VOLUME_START 16
//  VENT_VB0 13
//  INITIALIZE_SELECTOR_VALVE 14
//  SET_SELECTOR_VALVE 15
//  SET_DB_TIME 17
//  CALIB_FLOW 18
};
