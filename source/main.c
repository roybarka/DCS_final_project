#include  "../header/api.h"
#include  "../header/main.h"
#include  <stdio.h>




enum FSMstate state;
enum SYSmode lpm_mode;


void main(void){
  
  state = state8;
  lpm_mode = mode0;
  sysConfig();


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
	    Light_Detector();
        break;
    case state4:
        Object_and_Light_Detector();
        break;


	}
  }
}

  
  
  
  
  
  
