SystemReadMe.txt
MSP430 Embedded System - File Structure and Documentation
This document provides a comprehensive overview of all source files in the MSP430 embedded system project, 
including the purpose of each file and a brief explanation of all functions.

PROJECT STRUCTURE
Source Files (source directory):
	main.c - Main program logic and FSM implementation
	api.c - High-level API functions and system operations
	bsp.c - Board Support Package and hardware abstraction
	flash.c - Flash memory management and file operations
	halGPIO.c - Hardware Abstraction Layer for GPIO operations
	
Header Files (header directory):
	main.h - Main definitions, enums, and FSM state declarations
	api.h - API function prototypes and high-level declarations
	bsp.h - BSP function prototypes and hardware definitions
	flash.h - Flash memory function prototypes and structures
	halGPIO.h - GPIO hardware abstraction layer prototypes
	
Python GUI Application (/msp_gui directory):
	main.py - Entry point for the Python GUI application
	app.py - Main GUI application class and window management
	msp_controller.py - MSP430 communication controller
	modes - Individual operation mode implementations
	translators - Script encoding and protocol translators
	

main.c
main() - Initializes system and runs main FSM loop handling different detector and flash operation states


halGPIO.c
Interrupt Service Routines
TIMER1_A1_ISR() - Handles timer overflow for ultrasonic sensor timeout detection
TIMER1_A0_ISR() - Captures rising/falling edges for ultrasonic sensor echo timing
ADC10_ISR() - Exits low power mode when ADC conversion completes
Port_1_ISR() - Handles pushbutton presses for file navigation and LDR calibration
USCI0TX_ISR() - Disables UART TX interrupt when transmission completes
USCI0RX_ISR() - Processes received UART data and manages state transitions
Timer Functions
TIMER_A0_config() - Configures Timer A0 with specified counter value for delays
timer_delay_ms() - Creates precise millisecond delays using Timer A0
Timer_A0_ISR() - Timer A0 interrupt handler that exits low power mode
System Configuration
sysConfig() - Initializes all system components (GPIO, LCD, UART, ADC, flash)
telemetr_config() - Configures Timer A for servo PWM output
telemeter_deg_update() - Updates servo position based on received degree value
init_trigger_gpio() - Configures P1.7 as GPIO output for ultrasonic trigger
init_echo_capture() - Configures P2.0 for Timer1_A0 capture of ultrasonic echo
ADCconfig() - Configures ADC10 for LDR sensor readings
Measurement Functions
send_trigger_pulse() - Sends ultrasonic trigger pulse and measures echo time
LDRmeas() - Reads light sensor value using ADC
ser_output() - Sends string data via UART
LCD Functions
lcd_cmd() - Sends command to LCD controller
lcd_data() - Sends data character to LCD display
lcd_puts() - Displays string on LCD
lcd_init() - Initializes LCD controller for 4-bit mode
lcd_strobe() - Generates enable pulse for LCD communication



flash.c
ScriptData() - Calculates and stores file size for the last file
copy_seg_flash() - Writes file content to flash for the last file (backward compatibility)
copy_seg_flash_for_index() - Writes data to flash memory for specified file index with segment management
set_next_file_ptr() - Calculates and sets flash memory starting address for next file
save_LDR() - Stores LDR calibration measurement to flash memory
upload_files_from_flash() - Loads file structure from flash memory to RAM
download_files_to_flash() - Saves file structure from RAM to flash memory
bsp.c
GPIOconfig() - Configures all GPIO pins for servo, ultrasonic sensor, and LCD
PBconfig() - Configures pushbuttons as inputs with pull-ups and interrupts
StopAllTimers() - Halts all timer modules
UART_init() - Initializes UART communication at 9600 baud with 1MHz DCO


api.c
Output Helpers
send_meas() - Sends measurement data via UART in format "iteration:measurement"
send_two_meas() - Sends two measurements via UART in format "iteration:distance:light"
send_calib_progress() - Sends LDR calibration progress step number to PC
send_calib_done() - Sends completion message for LDR calibration
Main Detection Functions
Objects_Detector() - Performs 180-degree servo scan with ultrasonic distance measurements
Telemeter() - Measures distance at specific servo angle until angle changes
Light_Detector() - Performs 180-degree servo scan with LDR light measurements
Object_and_Light_Detector() - Performs 180-degree scan measuring both distance and light
Servo_Scan() - Scans servo between specified angles with distance measurements
LDRcalibrate() - Captures and stores LDR calibration measurements on button press
send_LDR_calibration_values() - Transmits stored LDR calibration values to PC
LCD Functions
testlcd() - Simple LCD test function displaying "this is a test"
count_up_LCD() - Increments and displays counter on LCD with delay
count_down_LCD() - Decrements and displays counter on LCD with delay
rrc_lcd() - Displays rotating character pattern across LCD lines
File Operations
display_file_info() - Shows file index, name, and type on LCD
display_file_content() - Displays file content on LCD with pagination
ReadFiles() - Main file reading function handling display updates
hex2int() - Converts 2-character hex string to integer value
RunScript() - Executes script commands from flash memory
ExecuteScript() - Main script execution function with file selection and running

bsp.c
GPIOconfig() - Configures all GPIO pins for servo PWM, ultrasonic sensor, LCD interface, and timer capture functionality
PBconfig() - Sets up pushbuttons as GPIO inputs with pull-up resistors and falling-edge interrupts
StopAllTimers() - Halts Timer_A0 and Timer_A1 by setting their control registers to stop mode
UART_init() - Initializes UART communication at 9600 baud using 1MHz DCO clock and configures USCI_A0 pins



HARDWARE COMPONENTS
Sensors:
LDR (Light Dependent Resistor): Connected to ADC channel for light measurement
Ultrasonic Sensor (HC-SR04): Trigger and echo pins for distance measurement
Servo Motor: PWM-controlled for 180° rotation
User Interface:
LCD Display: 16x2 character display for status and menu
Push Buttons: PB0 (next/forward), PB1 (select/back) for navigation
LEDs: Status indication and user feedback
Communication:
UART: Primary communication interface with PC GUI application
Flash Memory: Non-volatile storage for files and scripts