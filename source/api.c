#include  "../header/api.h"
#include  "../header/halGPIO.h"
#include "stdio.h"

unsigned int count_num = 0;
char string_lcd[5];

int deg;
int iter = 0;
int iter_meas = 0;
int deg_str;
int deg_duty_cycle;
unsigned int avg_meas;

//-------------------------------------------------------------
//                 Objects Detector
// TA0 in up-mode with TA0CCR0 = 20000 @ SMCLK=1MHz -> 20 ms period (50 Hz).
// Using TA0.1 (P1.6) with OUTMOD_7 (reset/set):
// pulse width [ticks] = TACCR1; 1 tick = 1 µs => 600..2400 ticks = 0.6..2.4 ms
// We map deg  [0..180] to CCR1 = 600 + 10*deg.
//------------------------------------------------------------
void  Objects_Detector(){
    init_trigger_gpio();
    init_echo_capture();
    __bis_SR_register(GIE);

    while(state==state1){
        int dist;
        deg = 600;
        TACCR1 = deg;
        TACCTL1 = OUTMOD_7;
        TACTL = TASSEL_2 | MC_1;
        TA1CTL = TASSEL_2 | MC_2;
        __delay_cycles(200000);
        for (iter = 0; iter < 180 && state==state1; iter++) {
                deg += 10;
                TACCR1 = deg;
                __delay_cycles(3000);
                for (iter_meas = 0; iter_meas < 7; iter_meas++) {
                    dist = send_trigger_pulse();
                    send_meas(dist,iter);
                    __delay_cycles(200);
                }

            }
    }

}
//-------------------------------------------------------------
//                Telemeter
//------------------------------------------------------------
void Telemeter(){
    deg = atoi(delay_array);
    deg_duty_cycle = 600 + deg * 10;
    TACCR1 = deg_duty_cycle;
    TACCTL1 = OUTMOD_7;
    TACTL = TASSEL_2 | MC_1;
    TA1CTL |= TASSEL_2 | MC_2;
    __delay_cycles(1000000);
    int j = 0;
    while(state==state2) {
        int dist = send_trigger_pulse();
        send_meas(dist,deg);
        __delay_cycles(1000000);
    }

    state=state8;
}

//-------------------------------------------------------------
//                Light_Detector
//------------------------------------------------------------

void Light_Detector(){
    while(state==state3){
        deg = 600;
        TACCR1 = deg;
        TACCTL1 = OUTMOD_7;
        TACTL = TASSEL_2 | MC_1;
        __delay_cycles(100000);
        for (iter = 0; iter < 180 && state==state3; iter++) {
            deg += 10;
            TACCR1 = deg;
            __delay_cycles(100000);
            avg_meas = LDRmeas();
            send_meas(avg_meas, iter);
            __delay_cycles(50000);

            }
    }

}
void Object_and_Light_Detector(){
    init_trigger_gpio();
    init_echo_capture();
    __bis_SR_register(GIE);

    while(state==state4){
        deg = 600;
        TACCR1 = deg;
        TACCTL1 = OUTMOD_7;
        TACTL = TASSEL_2 | MC_1;
        __delay_cycles(100000);
        for (iter = 0; iter < 180 && state==state4; iter++) {
            deg += 10;
            TACCR1 = deg;
            __delay_cycles(100000);
            avg_meas = LDRmeas();
            unsigned int dist = send_trigger_pulse();
            send_two_meas(iter,avg_meas, dist);
            __delay_cycles(50000);

            }
    }

}

