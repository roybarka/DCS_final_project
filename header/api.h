#ifndef _api_H_
#define _api_H_

#include "../header/bsp.h"
#include "../header/halGPIO.h"
#include "../header/main.h"

// Global variables
extern volatile unsigned int delay_time;  // Delay time in milliseconds for LCD operations

// =================== API FUNCTION PROTOTYPES ===================
void Objects_Detector(void);
void Telemeter(void);
void Light_Detector(void);
void Object_and_Light_Detector(void);
void Servo_Scan(unsigned int start_angle, unsigned int stop_angle);
void LDRcalibrate(void);
void send_meas(unsigned int meas, unsigned int iter);
void send_two_meas(unsigned int iter, unsigned int avg_meas, unsigned int dist);
void save_LDR(unsigned int meas, unsigned int counter);
void send_LDR_calibration_values(void);
void testlcd(void);
void ReadFiles(void);
void ExecuteScript(void);


#endif







