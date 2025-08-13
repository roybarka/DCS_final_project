// =================== INCLUDES ===================
#include "../header/halGPIO.h"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>

// =================== GLOBAL VARIABLES ===================
char delay_array[5];
int delay_flag = 0;
int state_flag = 0;
int change_deg = 0;
volatile int temp[2];
volatile float diff;
volatile unsigned int deg = 0;
volatile unsigned int deg_duty_cycle = 0;
volatile int meas_ready;
// ---- Capture state (shared with ISR) ----
volatile unsigned int t_rise = 0, t_fall = 0;
volatile unsigned int diff_ticks = 0;
volatile unsigned char cap_count = 0;
volatile unsigned char measure_done = 0;

// =================== INTERRUPT SERVICE ROUTINES ===================

// TIMER A1 ISR (Echo capture)
#pragma vector = TIMER1_A1_VECTOR
__interrupt void TIMER1_A1_ISR(void)
{
    switch (__even_in_range(TA1IV, TA1IV_TAIFG)) {
    case TA1IV_NONE: break;
    case TA1IV_TACCR1:
        if (cap_count == 0) {
            t_rise = TA1CCR1;
            cap_count = 1;
            __bic_SR_register_on_exit(LPM0_bits); // wake so you can see cap_count==1
        } else {
            t_fall = TA1CCR1;
            if (t_fall >= t_rise) diff_ticks = t_fall - t_rise;
            else                  diff_ticks = (unsigned)(t_fall + 65536u - t_rise);
            measure_done = 1;
            __bic_SR_register_on_exit(LPM0_bits); // wake main for the print
        }
        break;
    case TA1IV_TACCR2:  break;
    case TA1IV_TAIFG:  // Overflow timeout (~65 ms @ 1 MHz)
        diff_ticks   = 0;
        measure_done = 2;                    // mark timeout
        __bic_SR_register_on_exit(LPM0_bits);
        break;
    }
}

// ADC10 ISR
#pragma vector = ADC10_VECTOR
__interrupt void ADC10_ISR(void) {
    __bic_SR_register_on_exit(CPUOFF);
}

// UART TX ISR
#if defined(__TI_COMPILER_VERSION__) || defined(__IAR_SYSTEMS_ICC__)
#pragma vector=USCIAB0TX_VECTOR
__interrupt void USCI0TX_ISR(void)
#elif defined(__GNUC__)
void __attribute__ ((interrupt(USCIAB0TX_VECTOR))) USCI0TX_ISR (void)
#else
#error Compiler not supported!
#endif
{
    if(state == state5) UCA0TXBUF = '5';
    if(state == state9) UCA0TXBUF = '9';
    IE2 &= ~UCA0TXIE;                       // Disable USCI_A0 TX interrupt
}

// UART RX ISR
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
        static unsigned int j = 0;
        if (delay_flag == 1){
            delay_array[j] = UCA0RXBUF;
            j++;
            if (delay_array[j-1] == '\n'){
                j = 0;
                delay_flag = 0;
                state_flag = 0;
                state = state2;
                change_deg = 1;
            }
        } else {
            delay_flag = 1;
            state = state8;
        }
    }
    else if(UCA0RXBUF == '3' && delay_flag == 0){
        state = state3;
    }
    else if(UCA0RXBUF == '4' && delay_flag == 0){
        state = state4;
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
    case mode0: LPM0_EXIT; break;
    case mode1: LPM1_EXIT; break;
    case mode2: LPM2_EXIT; break;
    case mode3: LPM3_EXIT; break;
    case mode4: LPM4_EXIT; break;
    }
}

// =================== SYSTEM & HARDWARE CONFIGURATION ===================

void sysConfig(void){ 
    GPIOconfig();
    StopAllTimers();
    lcd_init();
    lcd_clear();
    UART_init();
    ADCconfig();
    __bis_SR_register(GIE);    // enable global interrupts
}

void telemetr_config(void)
{
    TACCTL1 = OUTMOD_7;
    TACTL = TASSEL_2 | MC_1;
    TA1CTL |= TASSEL_2 | MC_2;
}

void telemeter_deg_update(void)
{
    deg = atoi(delay_array);
    deg_duty_cycle = 600 + deg * 10;
    TACCR1 = deg_duty_cycle;
    change_deg = 0;
}

void init_trigger_gpio(void)
{
    P1SEL  &= ~BIT7;
    P1SEL2 &= ~BIT7;
    P1DIR  |=  BIT7;
    P1OUT  &= ~BIT7;
}

void init_echo_capture(void)
{
   P2SEL |= BIT1;
   P2DIR &= ~BIT1;
   TA1CTL = TASSEL_2 | MC_2 | TAIE;
   TA1CCTL1 = CM_3 | CCIS_0 | SCS | CAP | CCIE;
}

void ADCconfig(void)
{
    P1DIR &= ~(BIT4+BIT3);
    P1SEL |= (BIT4+BIT3);
    ADC10CTL0 = ADC10SHT_2 + ADC10ON + SREF_0 + ADC10IE;
    ADC10CTL1 = INCH_3 + ADC10SSEL_3;
    ADC10AE0 |= BIT3 + BIT4;
}

// =================== MEASUREMENT & HARDWARE ACCESS ===================

unsigned int send_trigger_pulse(void)
{
    cap_count    = 0;
    measure_done = 0;
    TA1CCTL1 &= ~(CCIFG | COV);
    TA1CTL   |= TACLR;
    TA1CTL |= TAIE;
    P1OUT |=  BIT7;
    __delay_cycles(200);
    P1OUT &= ~BIT7;
    while (!measure_done) {
        __bis_SR_register(LPM0_bits | GIE);
    }
    return diff_ticks;
}

unsigned int LDRmeas(void){
    ADC10CTL0 &= ~ENC;
    ADC10CTL1 = (ADC10CTL1 & ~INCH_7) | INCH_4;
    ADC10CTL0 |= ENC + ADC10SC;
    __bis_SR_register(LPM0_bits + GIE);
    unsigned int adc_value = ADC10MEM;
    unsigned int sum = adc_value;
    unsigned int avg_meas;
    ADC10CTL0 &= ~ENC;
    ADC10CTL1 = (ADC10CTL1 & ~INCH_7) | INCH_3;
    ADC10CTL0 |= ENC + ADC10SC;
    __bis_SR_register(LPM0_bits + GIE);
    adc_value = ADC10MEM;
    avg_meas = adc_value < sum ? adc_value : sum;
    return avg_meas;
}

void ser_output(char *str){
    while(*str != 0) {
        while (!(IFG2&UCA0TXIFG));
        UCA0TXBUF = *str++;
    }
}

// =================== LCD FUNCTIONS ===================

void lcd_cmd(unsigned char c){
    LCD_WAIT;
    if (LCD_MODE == FOURBIT_MODE)
    {
        LCD_DATA_WRITE &= ~OUTPUT_DATA;
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

void lcd_puts(const char * s){
    while(*s)
        lcd_data(*s++);
}

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

void lcd_strobe(){
  LCD_EN(1);
  asm("NOP");
  LCD_EN(0);
}

// =================== DELAY FUNCTIONS ===================

void DelayUs(unsigned int cnt){
    unsigned char i;
    for(i=cnt ; i>0 ; i--) asm("nop");
}

void DelayMs(unsigned int cnt){
    unsigned char i;
    for(i=cnt ; i>0 ; i--) DelayUs(1000);
}

void delay(unsigned int t){
    volatile unsigned int i;
    for(i=t; i>0; i--);
}

// =================== UTILITY FUNCTIONS ===================

void clear_string(char* str){
    int i;
    static unsigned int j = 0;
    for (i=0;i<16;i++){
        str[i]= 0;
    }
    j=0;
}
