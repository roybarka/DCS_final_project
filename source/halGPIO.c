#include  "../header/halGPIO.h"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>



char delay_array[5];
volatile unsigned int i;
int j=0;
int delay_flag = 0;
int state_flag = 0;
volatile int temp[2];
volatile float diff;

char newline[] = " \r\n";
char dst_char[5];
char deg_char[7];
volatile int meas_ready;

//--------------------------------------------------------------------
//             System Configuration  
//--------------------------------------------------------------------
void sysConfig(void){ 
	GPIOconfig();
	StopAllTimers();
	lcd_init();
	lcd_clear();
	UART_init();
	ADCconfig();
	__bis_SR_register(GIE);    // enable global interrupts
}
//--------------------------------------------------------------------


void ser_output(char *str){
    while(*str != 0) {
        while (!(IFG2&UCA0TXIFG));
        UCA0TXBUF = *str++;
    }
}
//--------------------------------------------------------------------
void ADCconfig(void){
    P1DIR &= ~(BIT4+BIT3);       // Set P2.4 to input
    P1SEL |= (BIT4+BIT3);
    // Configure ADC10
    ADC10CTL0 = ADC10SHT_2 + ADC10ON + SREF_0 + ADC10IE;  // 16-cycle sample, Vcc & GND ref, interrupt enable
    ADC10CTL1 = INCH_3 + ADC10SSEL_3;  // Input A3, clock = SMCLK
    ADC10AE0 |= BIT3 + BIT4;  // Enable analog input on P1.3 and P1.4
}
//*********************************************************************
//                        TIMER A1 ISR (Echo capture)
//*********************************************************************

#pragma vector = TIMER1_A1_VECTOR
 __interrupt void Timer_A(void) {
     temp[i] = TA1CCR1;
     i += 1;
     TA1CCTL1 &= ~CCIFG;
     TA1CCTL2 &= ~CCIFG;
     TA1CCTL0 &= ~CCIFG;
     if (i == 2) {
         unsigned int dt = (unsigned int)(temp[1] - temp[0]); // 16bit wrap
         diff = (float)((unsigned int)dt);
         //meas_ready = 1;
         i = 0;
     }
 }
 //*********************************************************************
 //                        ADC10 ISR
 //*********************************************************************
#pragma vector = ADC10_VECTOR
__interrupt void ADC10_ISR(void) {
    __bic_SR_register_on_exit(CPUOFF);
}
//--------------------------------------------------------------------

void send_trigger_pulse(int deg) {
    //TA1CCTL1 &= ~CCIFG;
    TA1CCTL1 &= ~CCIFG;
    TA1CTL |= TAIE;
    i = 0;
    meas_ready = 0;

    P1OUT |= BIT7;
    __delay_cycles(20);   // ~20µs at 1MHz: DCO=1MHz => 1us/cycle
    P1OUT &= ~BIT7;
    //while(meas_ready == 0){};
    __delay_cycles(20000);

    unsigned long ticks = (unsigned long)diff;
    ltoa(ticks, dst_char);
    ltoa(deg, deg_char);

    ser_output(deg_char);
    ser_output(":");
    ser_output(dst_char);
    ser_output(newline);
    //TA1CCTL1 &= ~CCIE;

}
//--------------------------------------------------------------------
void send_LDR(int meas, int iter){
    // Convert to string and print
    ltoa(iter, deg_char);
    ltoa(meas, dst_char);
    // Print descriptive text
    ser_output(deg_char);
    ser_output(":");
    ser_output(dst_char);
    ser_output(newline);
}
//--------------------------------------------------------------------

int LDRmeas(void){
    ADC10CTL0 &= ~ENC; //
    ADC10CTL1 = (ADC10CTL1 & ~INCH_7) | INCH_4;
    ADC10CTL0 |= ENC + ADC10SC;         // Start conversion
    __bis_SR_register(LPM0_bits + GIE); // Low Power Mode until ADC completes
    unsigned int adc_value = ADC10MEM;  // Get ADC result (0-1023)
    unsigned int sum = adc_value;
    unsigned int avg_meas;

    ADC10CTL0 &= ~ENC;
    ADC10CTL1 = (ADC10CTL1 & ~INCH_7) | INCH_3;
    ADC10CTL0 |= ENC + ADC10SC;         // Start conversion
    __bis_SR_register(LPM0_bits + GIE); // Low Power Mode until ADC completes
    adc_value = ADC10MEM;  // Get ADC result (0-1023)
    avg_meas = adc_value < sum ? adc_value : sum;
    //sum += adc_value;
    //avg_meas = sum / 2;
    return avg_meas;
}
//---------------------------------------------------------------------
//            LCD
//---------------------------------------------------------------------
//******************************************************************
// send a command to the LCD
//******************************************************************
void lcd_cmd(unsigned char c){

    LCD_WAIT;

    if (LCD_MODE == FOURBIT_MODE)
    {
        LCD_DATA_WRITE &= ~OUTPUT_DATA;// clear bits before new write
        LCD_DATA_WRITE |= ((c >> 4) & 0x0F) << LCD_DATA_OFFSET;
        lcd_strobe();
        LCD_DATA_WRITE &= ~OUTPUT_DATA;
        LCD_DATA_WRITE |= (c & (0x0F)) << LCD_DATA_OFFSET;
        lcd_strobe();
    }
    else
    {
        LCD_DATA_WRITE = c;
        lcd_strobe();
    }
}
//******************************************************************
// send data to the LCD
//******************************************************************
void lcd_data(unsigned char c){

    LCD_WAIT;

    LCD_DATA_WRITE &= ~OUTPUT_DATA;
    LCD_RS(1);
    if (LCD_MODE == FOURBIT_MODE)
    {
            LCD_DATA_WRITE &= ~OUTPUT_DATA;
            LCD_DATA_WRITE |= ((c >> 4) & 0x0F) << LCD_DATA_OFFSET;
            lcd_strobe();
            LCD_DATA_WRITE &= (0xF0 << LCD_DATA_OFFSET) | (0xF0 >> 8 - LCD_DATA_OFFSET);
            LCD_DATA_WRITE &= ~OUTPUT_DATA;
            LCD_DATA_WRITE |= (c & 0x0F) << LCD_DATA_OFFSET;
            lcd_strobe();
    }
    else
    {
            LCD_DATA_WRITE = c;
            lcd_strobe();
    }

    LCD_RS(0);
}
//******************************************************************
// write a string of chars to the LCD
//******************************************************************
void lcd_puts(const char * s){

    while(*s)
        lcd_data(*s++);
}
//******************************************************************
// initialize the LCD
//******************************************************************
void lcd_init(){

    char init_value;

    if (LCD_MODE == FOURBIT_MODE) init_value = 0x3 << LCD_DATA_OFFSET;
    else init_value = 0x3F;

    LCD_RS_DIR(OUTPUT_PIN);
    LCD_EN_DIR(OUTPUT_PIN);
    LCD_RW_DIR(OUTPUT_PIN);
    LCD_DATA_DIR |= OUTPUT_DATA;
    LCD_RS(0);
    LCD_EN(0);
    LCD_RW(0);

    DelayMs(15);
    LCD_DATA_WRITE &= ~OUTPUT_DATA;
    LCD_DATA_WRITE |= init_value;
    lcd_strobe();
    DelayMs(5);
    LCD_DATA_WRITE &= ~OUTPUT_DATA;
    LCD_DATA_WRITE |= init_value;
    lcd_strobe();
    DelayUs(200);
    LCD_DATA_WRITE &= ~OUTPUT_DATA;
    LCD_DATA_WRITE |= init_value;
    lcd_strobe();

    if (LCD_MODE == FOURBIT_MODE){
        LCD_WAIT;
        LCD_DATA_WRITE &= ~OUTPUT_DATA;
        LCD_DATA_WRITE |= 0x2 << LCD_DATA_OFFSET;
        lcd_strobe();
        lcd_cmd(0x28);
    }
    else lcd_cmd(0x3C);

    lcd_cmd(0xF);
    lcd_cmd(0x1);
    lcd_cmd(0x6);
    lcd_cmd(0x80);
}
//******************************************************************
// lcd strobe functions
//******************************************************************
void lcd_strobe(){
  LCD_EN(1);
  asm("NOP");
  LCD_EN(0);
}
//---------------------------------------------------------------------
//                     Polling delays
//---------------------------------------------------------------------
//******************************************************************
// Delay usec functions
//******************************************************************
void DelayUs(unsigned int cnt){

    unsigned char i;
    for(i=cnt ; i>0 ; i--) asm("nop"); // tha command asm("nop") takes raphly 1usec

}
//******************************************************************
// Delay msec functions
//******************************************************************
void DelayMs(unsigned int cnt){

    unsigned char i;
    for(i=cnt ; i>0 ; i--) DelayUs(1000); // tha command asm("nop") takes raphly 1usec

}
//******************************************************************
//            Polling based Delay function
//******************************************************************
void delay(unsigned int t){  //
    volatile unsigned int i;

    for(i=t; i>0; i--);
}

//*********************************************************************
//                           TX ISR
//*********************************************************************
#if defined(__TI_COMPILER_VERSION__) || defined(__IAR_SYSTEMS_ICC__)
#pragma vector=USCIAB0TX_VECTOR
__interrupt void USCI0TX_ISR(void)
#elif defined(__GNUC__)
void __attribute__ ((interrupt(USCIAB0TX_VECTOR))) USCI0TX_ISR (void)
#else
#error Compiler not supported!
#endif
{
//    if (state == state7) UCA0TXBUF = '7';
    if(state == state5) UCA0TXBUF = '5';
    if(state == state9) UCA0TXBUF = '9';
    IE2 &= ~UCA0TXIE;                       // Disable USCI_A0 TX interrupt
}


//*********************************************************************
//                         RX ISR
//*********************************************************************
#if defined(__TI_COMPILER_VERSION__) || defined(__IAR_SYSTEMS_ICC__)
#pragma vector=USCIAB0RX_VECTOR
__interrupt void USCI0RX_ISR(void)
#elif defined(__GNUC__)
void __attribute__ ((interrupt(USCIAB0RX_VECTOR))) USCI0RX_ISR (void)
#else
#error Compiler not supported!
#endif
{
    if (UCA0RXBUF == '1' && delay_flag == 0){
        state = state1;
    }

    else if(UCA0RXBUF == '2' || delay_flag){

        if (delay_flag == 1){
                    delay_array[j] = UCA0RXBUF;
                    j++;
                    if (delay_array[j-1] == '\n'){
                        j = 0;
                        delay_flag = 0;
                        state_flag = 0;
                        state = state2;

                    }
                }
                else{
                delay_flag = 1;
                }
    }
    else if(UCA0RXBUF == '3' && delay_flag == 0){
        state = state3;
    }
    else if(UCA0RXBUF == '5' && delay_flag == 0){
        state = state5;
    }
    else if(UCA0RXBUF == '6' && delay_flag == 0){
        state = state6;
    }
    else if(UCA0RXBUF == '7' && delay_flag == 0){
        state = state7;
    }
    else if(UCA0RXBUF == '8' && delay_flag == 0){
        state = state8;
    }
    else if(UCA0RXBUF == '9' && delay_flag == 0){
        state = state9;
        }



    switch(lpm_mode){
    case mode0:
        LPM0_EXIT; // must be called from ISR only
        break;
    case mode1:
        LPM1_EXIT; // must be called from ISR only
        break;
    case mode2:
        LPM2_EXIT; // must be called from ISR only
        break;
    case mode3:
        LPM3_EXIT; // must be called from ISR only
        break;
    case mode4:
        LPM4_EXIT; // must be called from ISR only
        break;
    }
}

void clear_string(char* str){
    int i;
    for (i=0;i<16;i++){
        str[i]= 0;
    }
    j=0;
}
