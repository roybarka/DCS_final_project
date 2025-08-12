#include  "../header/halGPIO.h"
#include  "../header/flash.h"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>



char deg_array[5];
volatile unsigned int i;
int j=0;
int delay_flag = 0;
int state_flag = 0;
volatile int temp[2];
volatile float diff;

char newline[] = " \r\n";
char dst_char[5];
char deg_char[7];
char Light_char[5];

volatile int meas_ready;
// ---- Capture state (shared with ISR) ----
volatile unsigned int t_rise = 0, t_fall = 0;
volatile unsigned int diff_ticks = 0;
volatile unsigned char cap_count = 0;
volatile unsigned char measure_done = 0;


char DataFromPC[RX_BUF_SIZE];
char file_content[RX_BUF_SIZE];

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

void init_trigger_gpio(void)
{
    // P1.7 as plain GPIO output (TRIG)  -- select I/O function
    P1SEL  &= ~BIT7;   // GPIO, not peripheral
    P1SEL2 &= ~BIT7;   // GPIO, not secondary function
    P1DIR  |=  BIT7;   // output direction
    P1OUT  &= ~BIT7;   // idle LOW (recommended by most HC-SR04 examples)
}

void init_echo_capture(void)
{
   // P2.1 -> TA1.1 CCI1A (ECHO input)
   P2SEL |= BIT1;            // select timer function on P2.1
   P2DIR &= ~BIT1;           // input

   // Timer1_A: SMCLK (1 MHz), continuous mode
   TA1CTL = TASSEL_2 | MC_2 | TAIE; // SMCLK, continuous up to 0xFFFF +TAIE: enable overflow interrupt (TAIFG)

   // CCR1 capture on both edges, input = CCI1A, synchronized, interrupt enabled
   TA1CCTL1 = CM_3 | CCIS_0 | SCS | CAP | CCIE;
}

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
__interrupt void TIMER1_A1_ISR(void)
{
    switch (__even_in_range(TA1IV, TA1IV_TAIFG)) {
    case TA1IV_NONE: break;
    case TA1IV_TACCR1:
        if (cap_count == 0) {
            t_rise = TA1CCR1;
            cap_count = 1;
            // DIAG: prove we got here at least once
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
    case TA1IV_TAIFG:  // overflow = timeout (~65.536 ms @ 1MHz)
            measure_done = 2;                            // mark "no echo"
            __bic_SR_register_on_exit(LPM0_bits);
            break;
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

unsigned int send_trigger_pulse() {
    {
        // Prepare capture state
        cap_count    = 0;
        measure_done = 0;
        TA1CCTL1 &= ~(CCIFG | COV);   // clear any pending flag/overflow
        TA1CTL   |= TACLR;            // reset TAR and divider to 0 before starting

        // Emit >=10 us HIGH pulse on TRIG (P1.7)
        P1OUT |=  BIT7;
        __delay_cycles(2000);   // ~12 �s at 1 MHz (meets > 10 �s spec)
        P1OUT &= ~BIT7;

        // Wait here until ISR captures both edges and signals completion.
        // Use LPM0 so SMCLK (Timer1_A clock) keeps running.
        while (!measure_done) {
            __bis_SR_register(LPM0_bits | GIE);
            __no_operation();
        }
        if (measure_done == 2) {
            ser_output("No echo / out of range\r\n");
            return;
        }

        /*
        // Convert microseconds to centimeters: us/58
        float distance_cm = ((float)diff_ticks) / 58.0f;   // HC-SR04 formula

        // Print "Distance: <int>.<frac> cm"
        char ibuf[8], fbuf[8], degbuf[8];
        unsigned int d_int  = (unsigned int)floorf(distance_cm);
        unsigned int d_frac = (unsigned int)floorf((distance_cm - d_int) * 100.0f + 0.5f); // 2 decimals

        //ser_output("Distance: ");
        ltoa(deg, degbuf);  ser_output(degbuf);
        ser_output(":");
        ltoa(diff_ticks, ibuf);  ser_output(ibuf);

        //if (d_frac < 10) ser_output("0");
        //ltoa(d_frac, fbuf); ser_output(fbuf);
        ser_output("\r\n");
        */
        return diff_ticks;
    }

}
//--------------------------------------------------------------------
void send_meas(unsigned int meas, unsigned int iter){
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

void send_two_meas(unsigned int iter,unsigned int avg_meas,unsigned int dist)
{
    // Convert to string and print
    ltoa(iter, deg_char);
    ltoa(avg_meas, Light_char);
    ltoa(dist, dst_char);

    ser_output(deg_char);
    ser_output(":");
    ser_output(dst_char);
    ser_output(":");
    ser_output(Light_char);
    ser_output(newline);
}

//--------------------------------------------------------------------

unsigned int LDRmeas(void){
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
    // Only process if character is valid ASCII (printable characters 32-126) or EOF character
    if ((UCA0RXBUF >= 32 && UCA0RXBUF <= 126) || UCA0RXBUF == EOF_CHAR) {
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
            case '8': state = state8; Main = detecor_sel; j = 0; break; // select detector 8
            default: j = 0; break; // reset input
            }

        break;

    case Tele_get_deg:
        if(DataFromPC[j-1] == RX_EOF_CHAR) {
            strcpy(deg_array, DataFromPC);
            state = state2; Main=detecor_sel;  j = 0;
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
                            if (expected_size > sizeof(file_content)) expected_size = sizeof(file_content);
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
///////////////
