#ifndef _api_H_
#define _api_H_

#include "../header/bsp.h"
#include "../header/halGPIO.h"
#include "../header/main.h"

// =================== API FUNCTION PROTOTYPES ===================
void Objects_Detector(void);
void Telemeter(void);
void Light_Detector(void);
void Object_and_Light_Detector(void);
void LDRcalibrate(void);
void send_meas(unsigned int meas, unsigned int iter);
void send_two_meas(unsigned int iter, unsigned int avg_meas, unsigned int dist);
void save_LDR(unsigned int meas, unsigned int counter);
void send_LDR_calibration_values(void);
void testlcd(void);
void ReadFiles(void);


#endif







