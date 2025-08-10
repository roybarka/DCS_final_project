// Connections
// P2.1 ECHO (Timer1_A capture input)
// P1.6 TRIGGER (manual GPIO pulse output)

#include <msp430.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>

char printdist[] = "Distance to the nearest object is: ";
char centimeter[] = " cm";
char dot[] = ".";
char zerro[] = "0";
char deg_pres[] = "deg of meas is: ";
char newline[] = " \r\n";
volatile int temp[2];
volatile float diff;
volatile unsigned int i=0;
int dst_int;
int dst_flt,deg;
float tmp_flt;
char dst_char[5];
char deg_char[7];
char dst_flt_char[5];
volatile float distance;

void ser_output(char *str);

void send_trigger_pulse(void) {
    P1OUT |= BIT7;            // Set trigger HIGH
    __delay_cycles(2000);       // Wait ~20 cycles (~20us at 1MHz, 10 is fine but 20 is safe for HC-SR04)
    P1OUT &= ~BIT7;           // Set trigger LOW
}

void main(void)
{
    WDTCTL = WDTPW | WDTHOLD;   // stop watchdog timer

    if (CALBC1_1MHZ==0xFF) while(1);

    DCOCTL = 0;
    BCSCTL1 = CALBC1_1MHZ;
    DCOCTL = CALDCO_1MHZ;

    //PWM
    P1DIR |= BIT6;
    P1SEL |= BIT6;  //selection for timer setting
    TACCR0 = 20000;  //PWM period

    // Setup TRIGGER pin (P1.7) as GPIO output
    P1DIR |= BIT7;
    P1OUT &= ~BIT7;
    P1SEL &= ~BIT7;

    // Setup ECHO pin (P2.1) as Timer1_A capture input
    P2SEL |= BIT1;       // P2.1 as TA1.1 (capture input)
    P2DIR &= ~BIT1;      // Ensure as input

    // UART setup (unchanged)
    P1OUT &= 0x00;
    P1SEL |= BIT1|BIT2;
    P1SEL2 |= BIT1|BIT2;
    UCA0CTL1 |= UCSSEL_2;
    UCA0BR0 = 104;
    UCA0BR1 = 0x00;
    UCA0MCTL = UCBRS0;
    UCA0CTL1 &= ~UCSWRST;

    // echo timer config (only TA1 is used!)
    TA1CTL = TASSEL_2|MC_2 ;
    TA1CCTL1 = CAP | CCIE | CCIS_0 | CM_3 | SCS ;
    _enable_interrupts();

    while(1){
        for (deg=600; deg<2500; deg = deg+10){
                   TACCR1 = deg;  //CCR1 PWM Duty Cycle  !min 350 max 2600 angle 190,
                   //350 2350-180 degrees
                   TACCTL1 = OUTMOD_7;  //CCR1 selection reset-set
                   TACTL = TASSEL_2|MC_1;   //SMCLK submain clock,upmode


                   send_trigger_pulse(); // Send a manual trigger pulse

                   __delay_cycles(30000); // Give sensor time to reply (~30ms, tune as needed)

                   distance = diff/58;
                   dst_int = floor(distance);
                   tmp_flt = distance - dst_int;
                   ltoa(dst_int, dst_char);
                   ltoa(deg, deg_char);
                   if (tmp_flt < 0.01) {
                       dst_flt = floor(tmp_flt * 1000);
                       ltoa(dst_flt,dst_flt_char);
                       ser_output(printdist); ser_output(dst_char); ser_output(dot); ser_output(zerro); ser_output(zerro); ser_output(dst_flt_char); ser_output(centimeter);
                       ser_output(newline); ser_output(deg_pres); ser_output(deg_char);
                   }
                   else if (tmp_flt < 0.1) {
                       dst_flt = floor(tmp_flt * 100);
                       ltoa(dst_flt,dst_flt_char);
                       ser_output(printdist); ser_output(dst_char); ser_output(dot); ser_output(zerro); ser_output(dst_flt_char); ser_output(centimeter);
                       ser_output(newline); ser_output(deg_pres); ser_output(deg_char);
                   }
                   else {
                       dst_flt = floor(tmp_flt * 100);
                       ltoa(dst_flt,dst_flt_char);
                       ser_output(printdist); ser_output(dst_char); ser_output(dot); ser_output(dst_flt_char); ser_output(centimeter);
                       ser_output(newline); ser_output(deg_pres); ser_output(deg_char);
                   }
                   ser_output(newline);
                   __delay_cycles(5000);  //0.5 second delay
                     }



           for (deg; deg>600; deg = deg-10){
               TACCR1 = deg;  //CCR1 PWM Duty Cycle  !min 350 max 2600 angle 190,
               //350 2350-180 degrees
               TACCTL1 = OUTMOD_7;  //CCR1 selection reset-set
               TACTL = TASSEL_2|MC_1;   //SMCLK submain clock,upmode
               send_trigger_pulse(); // Send a manual trigger pulse

               __delay_cycles(30000); // Give sensor time to reply (~30ms, tune as needed)

               distance = diff/58;
               dst_int = floor(distance);
               tmp_flt = distance - dst_int;
               ltoa(dst_int, dst_char);
               ltoa(deg, deg_char);
               if (tmp_flt < 0.01) {
                   dst_flt = floor(tmp_flt * 1000);
                   ltoa(dst_flt,dst_flt_char);
                   ser_output(printdist); ser_output(dst_char); ser_output(dot); ser_output(zerro); ser_output(zerro); ser_output(dst_flt_char); ser_output(centimeter);
                   ser_output(newline); ser_output(deg_pres); ser_output(deg_char);
               }
               else if (tmp_flt < 0.1) {
                   dst_flt = floor(tmp_flt * 100);
                   ltoa(dst_flt,dst_flt_char);
                   ser_output(printdist); ser_output(dst_char); ser_output(dot); ser_output(zerro); ser_output(dst_flt_char); ser_output(centimeter);
                   ser_output(newline); ser_output(deg_pres); ser_output(deg_char);
               }
               else {
                   dst_flt = floor(tmp_flt * 100);
                   ltoa(dst_flt,dst_flt_char);
                   ser_output(printdist); ser_output(dst_char); ser_output(dot); ser_output(dst_flt_char); ser_output(centimeter);
                   ser_output(newline); ser_output(deg_pres); ser_output(deg_char);
               }
               ser_output(newline);
               __delay_cycles(5000);  //0.5 second delay
           }
           }



      }

#pragma vector = TIMER1_A1_VECTOR
__interrupt void Timer_A(void){
    temp[i] = TA1CCR1;
    i += 1;
    TA1CCTL1 &= ~CCIFG ;
    if (i==2) {
        diff=temp[i-1]-temp[i-2];
        i=0;
    }
}

void ser_output(char *str){
    while(*str != 0) {
        while (!(IFG2&UCA0TXIFG));
        UCA0TXBUF = *str++;
    }
}
