#include <msp430.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

// ----------------------------
// Generator (Input Capture on P2.4)
// ----------------------------
#define GenPort          P1IN
#define GenPortSel       P1SEL
#define GenPortDir       P1DIR
#define GenPortOut       P1OUT

int avg_meas;

void ser_output(char *str);
void ADCconfig(void);
int LDRmeas(void);
void send_LDR(int);

void main(void)
{
    WDTCTL = WDTPW | WDTHOLD;   // Stop watchdog timer

    // Clock to 1MHz
    BCSCTL1 = CALBC1_1MHZ;
    DCOCTL = CALDCO_1MHZ;

    // UART config
    P1SEL = BIT1 | BIT2;
    P1SEL2 = BIT1 | BIT2;
    UCA0CTL1 |= UCSSEL_2;       // SMCLK
    UCA0BR0 = 104;              // 9600 baud
    UCA0BR1 = 0x00;
    UCA0MCTL = UCBRS0;
    UCA0CTL1 &= ~UCSWRST;

    // Generator (Input Capture at P2.4)
    GenPortDir &= ~(BIT4+BIT3);       // Set P2.4 to input
    GenPortSel |= (BIT4+BIT3);        // Enable special function

    /*
    // Configure ADC10
    ADC10CTL0 = ADC10SHT_2 + ADC10ON + SREF_0 + ADC10IE;  // 16-cycle sample, Vcc & GND ref, interrupt enable
    ADC10CTL1 = INCH_3 + ADC10SSEL_3;  // Input A3, clock = SMCLK
    ADC10AE0 |= BIT3 + BIT4;  // Enable analog input on P1.3 and P1.4
    */
    ADCconfig();

    _enable_interrupts();
    while(1){
        avg_meas = LDRmeas();
        send_LDR(avg_meas);
        __delay_cycles(500000); // delay ~0.5s
        /*
        ADC10CTL0 &= ~ENC; // חובה לכבות ENC לפני שינוי INCH
        ADC10CTL1 = (ADC10CTL1 & ~INCH_7) | INCH_4;
        ADC10CTL0 |= ENC + ADC10SC;         // Start conversion
        __bis_SR_register(LPM0_bits + GIE); // Low Power Mode until ADC completes
        unsigned int adc_value = ADC10MEM;  // Get ADC result (0-1023)
        int sum = adc_value;

        ADC10CTL0 &= ~ENC;
        ADC10CTL1 = (ADC10CTL1 & ~INCH_7) | INCH_3;
        ADC10CTL0 |= ENC + ADC10SC;         // Start conversion
        __bis_SR_register(LPM0_bits + GIE); // Low Power Mode until ADC completes
        adc_value = ADC10MEM;  // Get ADC result (0-1023)
        sum += adc_value;
        avg_meas = sum / 2;


        // Convert to string and print
        char buffer[16];
        ltoa(avg_meas, buffer);
        // Print descriptive text
        ser_output("Average ADC Reading on P1.3 and P1.4: ");
        ser_output(buffer);
        ser_output(" (0-1023 scale)\r\n");

        __delay_cycles(500000); // delay ~0.5s
        */
    }
}

void send_LDR(int meas){
    // Convert to string and print
    char buffer[16];
    ltoa(meas, buffer);
    // Print descriptive text
    ser_output("Average ADC Reading on P1.3 and P1.4: ");
    ser_output(buffer);
    ser_output(" (0-1023 scale)\r\n");
}

int LDRmeas(void){
    ADC10CTL0 &= ~ENC; // חובה לכבות ENC לפני שינוי INCH
    ADC10CTL1 = (ADC10CTL1 & ~INCH_7) | INCH_4;
    ADC10CTL0 |= ENC + ADC10SC;         // Start conversion
    __bis_SR_register(LPM0_bits + GIE); // Low Power Mode until ADC completes
    unsigned int adc_value = ADC10MEM;  // Get ADC result (0-1023)
    int sum = adc_value;

    ADC10CTL0 &= ~ENC;
    ADC10CTL1 = (ADC10CTL1 & ~INCH_7) | INCH_3;
    ADC10CTL0 |= ENC + ADC10SC;         // Start conversion
    __bis_SR_register(LPM0_bits + GIE); // Low Power Mode until ADC completes
    adc_value = ADC10MEM;  // Get ADC result (0-1023)
    sum += adc_value;
    avg_meas = sum / 2;
    return avg_meas;
}


void ADCconfig(void){
    // Configure ADC10
    ADC10CTL0 = ADC10SHT_2 + ADC10ON + SREF_0 + ADC10IE;  // 16-cycle sample, Vcc & GND ref, interrupt enable
    ADC10CTL1 = INCH_3 + ADC10SSEL_3;  // Input A3, clock = SMCLK
    ADC10AE0 |= BIT3 + BIT4;  // Enable analog input on P1.3 and P1.4
}


void ser_output(char *str){
    while(*str != 0) {
        while (!(IFG2&UCA0TXIFG));
        UCA0TXBUF = *str++;
    }
}

#pragma vector = ADC10_VECTOR
__interrupt void ADC10_ISR(void) {
    __bic_SR_register_on_exit(CPUOFF);
}
