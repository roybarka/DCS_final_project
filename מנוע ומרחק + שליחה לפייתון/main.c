// Connections
// P2.1 ECHO (Timer1_A capture input)
// P1.6 PWM
// P1.7 TRIGGER (manual GPIO pulse output)

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

// --- Prototypes ---
void init_clock(void);
void init_uart(void);
void init_trigger_echo(void);
void init_pwm(void);
void send_trigger_pulse(void);
void send_distance_uart(void);
void rotate_motor_and_measure(void);
void ser_output(char *str);

// --- Main ---
void main(void)
{
    WDTCTL = WDTPW | WDTHOLD;

    if (CALBC1_1MHZ == 0xFF)
        while (1);

    init_clock();
    init_uart();
    init_trigger_echo();
    init_pwm();
    _enable_interrupts();

    while (1) {
        rotate_motor_and_measure();
    }
}


// --- Functions ---

void init_clock(void) {
    DCOCTL = 0;
    BCSCTL1 = CALBC1_1MHZ;
    DCOCTL = CALDCO_1MHZ;
}


void init_uart(void) {
    P1OUT &= 0x00;
    P1SEL |= BIT1 | BIT2;
    P1SEL2 |= BIT1 | BIT2;
    UCA0CTL1 |= UCSSEL_2;
    UCA0BR0 = 104;
    UCA0BR1 = 0x00;
    UCA0MCTL = UCBRS0;
    UCA0CTL1 &= ~UCSWRST;
}

void init_trigger_echo(void) {
    // Trigger pin (P1.7)
    P1DIR |= BIT7;
    P1OUT &= ~BIT7;
    P1SEL &= ~BIT7;

    // Echo pin (P2.1)
    P2SEL |= BIT1;
    P2DIR &= ~BIT1;

    // Timer1_A Capture for Echo
    TA1CTL = TASSEL_2 | MC_2;
    TA1CCTL1 = CAP | CCIE | CCIS_0 | CM_3 | SCS;
}

void init_pwm(void) {
    P1DIR |= BIT6;
    P1SEL |= BIT6;
    TACCR0 = 20000; // 20ms PWM period
}

void send_trigger_pulse(void) {
    P1OUT |= BIT7;
    __delay_cycles(2000);  // ~20µs at 1MHz
    P1OUT &= ~BIT7;
}

void rotate_motor_and_measure(void) {
    int flag = 1;
    // Forward
    for (deg = 600; deg < 2500; deg += 10) {
        TACCR1 = deg;
        TACCTL1 = OUTMOD_7;
        TACTL = TASSEL_2 | MC_1;

        send_trigger_pulse();
        __delay_cycles(30000);
        send_distance_uart();
        __delay_cycles(50000);
        if(flag){
            deg++;
              }
        flag = ~flag;
    }

    // Backward
    for (; deg > 600; deg -= 10) {
        TACCR1 = deg;
        TACCTL1 = OUTMOD_7;
        TACTL = TASSEL_2 | MC_1;

        send_trigger_pulse();
        __delay_cycles(30000);
        send_distance_uart();
        __delay_cycles(50000);
        if(flag){
                deg--;
                  }
            flag = ~flag;
    }
}

void send_distance_uart(void) {
    distance = diff / 58;
    dst_int = floor(distance);
    tmp_flt = distance - dst_int;

    ltoa(dst_int, dst_char);
    ltoa(deg, deg_char);

    ser_output(deg_char);
    ser_output(":");
    ser_output(dst_char);
    ser_output(newline);
}


// Timer1_A1 ISR – Capture Echo
#pragma vector = TIMER1_A1_VECTOR
__interrupt void Timer_A(void) {
    temp[i] = TA1CCR1;
    i += 1;
    TA1CCTL1 &= ~CCIFG;
    if (i == 2) {
        diff = temp[1] - temp[0];
      // if (diff < 0) diff += 65536;  // handle overflow
        i = 0;
    }
}

void ser_output(char *str){
    while(*str != 0) {
        while (!(IFG2&UCA0TXIFG));
        UCA0TXBUF = *str++;
    }
}
