// =================== INCLUDES ===================
#include "../header/halGPIO.h"
#include  "../header/flash.h"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>

// =================== GLOBAL VARIABLES ===================
char deg_array[5];
int j=0;
int delay_flag = 0;
int state_flag = 0;
int change_deg = 0;
volatile int temp[2];
volatile float diff;
volatile unsigned char pb_pressed = 0;
volatile unsigned int measureCounter = 0;
volatile unsigned int deg = 0;
volatile unsigned int deg_duty_cycle = 0;
volatile int meas_ready;
// ---- Capture state (shared with ISR) ----
volatile unsigned int t_rise = 0, t_fall = 0;
volatile unsigned int diff_ticks = 0;
volatile unsigned char cap_count = 0;
volatile unsigned char measure_done = 0;

char DataFromPC[RX_BUF_SIZE];
char file_content[RX_BUF_SIZE];

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

// TIMER A1 ISR (Echo capture) -for P2.0
#pragma vector = TIMER1_A0_VECTOR
__interrupt void TIMER1_A0_ISR(void)
{
    if (cap_count == 0) {
        t_rise = TA1CCR0;               // read CCR0
        cap_count = 1;
        __bic_SR_register_on_exit(LPM0_bits);
    } else {
        t_fall = TA1CCR0;               // read CCR0
        if (t_fall >= t_rise) diff_ticks = t_fall - t_rise;
        else                  diff_ticks = (unsigned)(t_fall + 65536u - t_rise);
        measure_done = 1;
        __bic_SR_register_on_exit(LPM0_bits);
    }
}

// ADC10 ISR
#pragma vector = ADC10_VECTOR
__interrupt void ADC10_ISR(void) {
    __bic_SR_register_on_exit(CPUOFF);
}


// Port 1 interrupt service routine
#pragma vector=PORT1_VECTOR
__interrupt void Port_1_ISR(void){
    delay(debounceVal);
    if (P1IFG & BIT0) {  // Check if interrupt was triggered by P1.0 (PB0)
        if (state == state6) {
            pb_pressed = 1;  // Set flag for main loop
        }
        P1IFG &= ~BIT0;  // Clear P1.3 interrupt flag
    }
    __bic_SR_register_on_exit(LPM0_bits);  // Exit LPM0
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
    // Only process if character is valid ASCII (printable characters 32-126) or EOF character
    if ((UCA0RXBUF >= 32 && UCA0RXBUF <= 126) || UCA0RXBUF == EOF_CHAR || UCA0RXBUF == RX_EOF_CHAR) {
    DataFromPC[j] = UCA0RXBUF;  // Get string from PC
    j++;
    } else {
        return; // Exit ISR early if invalid character
    }

    switch(Main){
    case detecor_sel:
        switch (DataFromPC[0]) {
            case '1': state = state1; Main = detecor_sel; j = 0; break; // select detector 1
            case '2': Main = Tele_get_deg; j = 0; break; // go to get degree
            case '3': state = state3; Main = detecor_sel; j = 0; break; // select detector 3
            case '4': state = state4; Main = detecor_sel; j = 0; break; // select detector 4
            case '5': Main = Flash; flash_state = Flash_SelectOp; j = 0; break; // enter flash menu
            case '6': state = state6; Main = detecor_sel; j = 0; break; // enter LDR calibration
            case '8': state = state8; Main = detecor_sel; j = 0; break; // select detector 8
            default: j = 0; break; // reset input
            }

        break;

    case Tele_get_deg:
        if(DataFromPC[j-1] == RX_EOF_CHAR) {
            strcpy(deg_array, DataFromPC);
            state = state2; Main=detecor_sel;
            j = 0;
            change_deg = 1;
        }
        break;

    case Flash:
        // Simple second-level FSM for flash operations; transitions only
        switch (flash_state) {
            case Flash_SelectOp:
                // Expect: 'r' (read), 'e' (execute), 'w' (write)
                if (DataFromPC[0] == 'r') { flash_state = Flash_Reading; j = 0; }
                else if (DataFromPC[0] == 'e') { flash_state = Flash_Executing; j = 0; }
                else if (DataFromPC[0] == 'w') { flash_state = Flash_Writing; write_stage = Write_WaitName; j = 0; }
                else {j = 0;}
                break;

            case Flash_Reading:
                // Placeholder: upon newline, return to selector
                if (DataFromPC[j-1] == RX_EOF_CHAR) { flash_state = Flash_SelectOp; j = 0; }
                break;

            case Flash_Executing:
                // Placeholder: upon newline, return to selector
                if (DataFromPC[j-1] == RX_EOF_CHAR) { flash_state = Flash_SelectOp; j = 0; }
                break;

            case Flash_Writing:
            {
                static short current_file_index = 0;   // select slot 0 for now
                static unsigned int expected_size = 0; // number of bytes to receive
                static unsigned int received_size = 0; // progress counter
                if (DataFromPC[j-1] == RX_EOF_CHAR || DataFromPC[j-1] == EOF_CHAR || j == RX_BUF_SIZE) {
                    switch (write_stage) {
                        case Write_WaitName:
                            // Start a new file in the next free slot
                            current_file_index = (file.num_of_files < 10) ? file.num_of_files : 9;
                            // Set the flash pointer for this file
                            set_next_file_ptr(current_file_index);
                            // Initialize current write position to 0 (will be set to file start on first write)
                            current_write_positions[current_file_index] = 0;
                            // Copy name (strip trailing newline) into file table
                            {
                                unsigned int name_len = (unsigned int)(j - 1);
                                if (name_len > 10) name_len = 10;
                                memset(file.file_name[current_file_index], 0, sizeof(file.file_name[current_file_index]));
                                memcpy(file.file_name[current_file_index], DataFromPC, name_len);
                                write_stage = Write_WaitType;
                                j = 0;
                            }
                            break;
                        case Write_WaitType:
                            // Type is first char '0' or '1'
                            file.file_type[current_file_index] = (DataFromPC[0] == '1') ? text : script;
                            write_stage = Write_WaitSize;
                            j = 0;
                            break;
                        case Write_WaitSize:
                            // Parse decimal size up to buffer limit
                            expected_size = (unsigned int)atoi(DataFromPC);
                            file.file_size[current_file_index] = (int)expected_size;
                            received_size = 0;
                            memset(file_content, 0, sizeof(file_content));
                            write_stage = Write_WaitContent;
                            j = 0;
                            break;
                        case Write_WaitContent:
                            // Check which character ended the input
                            if (DataFromPC[j-1] == RX_EOF_CHAR || j == RX_BUF_SIZE) {
                                // End of chunk - write current data to flash and continue
                                unsigned int chunk_len = (unsigned int)(j - 1);
                                if (received_size + chunk_len > expected_size) {
                                    chunk_len = expected_size - received_size;
                                }
                                memcpy(&file_content[received_size], DataFromPC, chunk_len);
                                received_size += chunk_len;

                                // Write current chunk to flash
                                copy_seg_flash_for_index(current_file_index, file_content, received_size);
                                j = 0;

                                // Continue waiting for more content if not finished
                                if (received_size < expected_size) {
                                    // Reset for next chunk
                                    memset(file_content, 0, sizeof(file_content));
                                    received_size = 0;
                                }
                            } else if (DataFromPC[j-1] == EOF_CHAR) {
                                // End of file - write final chunk and advance to next file
                                unsigned int chunk_len = (unsigned int)(j - 1);
                                if (received_size + chunk_len > expected_size) {
                                    chunk_len = expected_size - received_size;
                                }
                                memcpy(&file_content[received_size], DataFromPC, chunk_len);
                                received_size += chunk_len;

                                // Write final data to flash
                                copy_seg_flash_for_index(current_file_index, file_content, received_size);

                                // Advance counters for next file
                                if (file.num_of_files < 10) {
                                    if (current_file_index >= file.num_of_files) {
                                        file.num_of_files = current_file_index + 1;
                                    }
                                    if (current_file_index < 9) {
                                        current_file_index++;
                                    }
                                }
                                flash_state = Flash_SelectOp;
                                write_stage = Write_WaitName;
                                Main = detecor_sel;
                                j = 0;
                            }
                            break;
                    }
                }
                break;
            }
        }
        break;
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
    PBconfig();
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
    deg = atoi(deg_array);
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
    P2SEL |= BIT0;          // use P2.0 as TA1.0 CCI0A
    P2DIR &= ~BIT0;         // input
    TA1CTL   = TASSEL_2 | MC_2;                 // SMCLK, continuous, overflow IRQ
    TA1CCTL0 = CM_3 | CCIS_0 | SCS | CAP | CCIE;       // both edges on CCI0A, sync, capture, IRQ
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
    TA1CCTL0 &= ~(CCIFG | COV);   // <-- CCR0 instead of CCR1
    TA1CTL   |= TACLR;
    P1OUT |=  BIT7;
    __delay_cycles(200);
    P1OUT &= ~BIT7;
    TA1CTL |= TAIE; // enable overflow iterupts (for if echo didnt reurn twice)
    while (!measure_done) {
        __bis_SR_register(LPM0_bits | GIE);
    }
    TA1CTL   &= ~TAIE; // disable overflow iterupts (for if echo didnt reurn twice)
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

