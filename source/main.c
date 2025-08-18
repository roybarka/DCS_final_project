#include "../header/api.h"
#include "../header/main.h"
#include  "../header/flash.h"

#include  <stdio.h>

enum FSMstate state;
enum main_states Main;
enum flash_states flash_state;
enum write_stages write_stage;
enum read_stages read_stage;

enum SYSmode lpm_mode;
int p = 0;


void main(void){
  Main = detecor_sel;
  state = state8;
  read_stage = Read_FileSelect;
  lpm_mode = mode0;
  sysConfig();

  // Initialize current_write_positions array to all zeros
  for ( p = 0; p < 10; p++) {
      current_write_positions[p] = 0;
  }


  while(1){
    switch(state){
    case state8:
        IE2 |= UCA0RXIE;
        __bis_SR_register(LPM0_bits + GIE);
        break;
    case state1:
        Objects_Detector();
        break;
    case state2:
        Telemeter();
        break;
    case state3:
        send_LDR_calibration_values();
        Light_Detector();
        break;
    case state4:
        send_LDR_calibration_values();
        Object_and_Light_Detector();
        break;
    case state6:
        LDRcalibrate();
        __bis_SR_register(LPM0_bits + GIE);
        break;
    case state7:
        ReadFiles();  // This function handles both display and sleep mode
        __bis_SR_register(LPM0_bits + GIE);
        break;

    }
  }
}
