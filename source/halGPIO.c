// =================== INCLUDES ===================
#include "../header/halGPIO.h"
#include  "../header/flash.h"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>

// =================== GLOBAL VARIABLES ===================
char deg_array[5];
char j=0;
char change_deg = 0;
char exit_flag  = 0;
volatile int temp[2];

// Flash reading state variables
volatile unsigned char current_file_idx = 0;     // Current file being viewed/selected
volatile unsigned int current_read_pos = 0;      // Current position in file for display
volatile unsigned char display_update_req = 0;   // Flag to indicate display needs updating
volatile float diff;
volatile unsigned char pb_pressed = 0;
volatile unsigned int measureCounter = 0;
volatile unsigned char waitready = 0;
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

// TIMER1_A1_VECTOR - Only handles timer overflow for timeout detection
#pragma vector = TIMER1_A1_VECTOR
__interrupt void TIMER1_A1_ISR(void)
{
    // Get the interrupt vector value
    unsigned int iv = TA1IV;
    
    // Check for timer overflow (TAIFG)
    if (iv == TA1IV_TAIFG) {
        // Overflow timeout occurred (~65 ms @ 1 MHz) - No echo detected
        diff_ticks   = 0;
        measure_done = 2;  // mark as timeout
        
        // Clear the overflow flag (though reading TA1IV should have cleared it)
        TA1CTL &= ~TAIFG;
        
        // Exit low power mode
        __bic_SR_register_on_exit(LPM0_bits);
    }
}

// TIMER1_A0_VECTOR - Only handles capturing edges on TA1CCR0 (P2.0)
#pragma vector = TIMER1_A0_VECTOR
__interrupt void TIMER1_A0_ISR(void)
{
    if (cap_count == 0) {
        // First edge (rising edge) detected
        t_rise = TA1CCR0;               // read CCR0
        cap_count = 1;
        __bic_SR_register_on_exit(LPM0_bits); // Exit low power mode
    } else {
        // Second edge (falling edge) detected
        t_fall = TA1CCR0;               // read CCR0
        
        // Calculate time difference with overflow handling
        if (t_fall >= t_rise) {
            diff_ticks = t_fall - t_rise;
        } else {
            diff_ticks = (unsigned)(t_fall + 65536u - t_rise);
        }
        
        measure_done = 1;  // Mark measurement as complete
        __bic_SR_register_on_exit(LPM0_bits); // Exit low power mode
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
    delay(debounceVal);
    delay(debounceVal);

    // Handle Flash Reading and Executing states
    if (flash_state == Flash_Reading) {
        if (read_stage == Read_FileSelect) {
            if (P1IFG & PB0) {
                // Move to next file (with wrap-around)
                current_file_idx++;
                if (current_file_idx >= file.num_of_files) {current_file_idx = 0;                }
                display_update_req = 1;  // Request display update
            }
            else if (P1IFG & PB1) {
                // Select current file if it's a text file
                if (file.file_type[current_file_idx] == text) {
                    read_stage = Read_FileDisplay;
                    current_read_pos = 0;  // Start from beginning of file
                    display_update_req = 1;  // Request display update
                }
            }
        }
        else if (read_stage == Read_FileDisplay) {
            if (P1IFG & PB0) {
                // Move to next page if there's more content
                if (current_read_pos < file.file_size[current_file_idx]) {
                    current_read_pos += 32;  // Move forward by display width
                    if (current_read_pos > file.file_size[current_file_idx]) {
                        current_read_pos = file.file_size[current_file_idx];
                    }
                    display_update_req = 1;  // Request display update
                }
            }
            else if (P1IFG & PB1) {
                // Return to file selection
                read_stage = Read_FileSelect;
                current_read_pos = 0;
                display_update_req = 1;  // Request display update
            }
        }
    }
    // Handle Execute state
    else if (flash_state == Flash_Executing && execute_stage == Execute_FileSelect) {
        if (P1IFG & PB0) {
            // Move to next file (with wrap-around)
            current_file_idx++;
            if (current_file_idx >= file.num_of_files) {
                current_file_idx = 0;
            }
            display_update_req = 1;  // Request display update
        }
        else if (P1IFG & PB1) {
            // Select current file if it's a script file
            if (file.file_type[current_file_idx] == script) {
                execute_stage = Execute_Running;
                state = state9;  // Switch to execute state
                display_update_req = 1;
            }
        }
    }
    // Handle LDR calibration
    else if ((P1IFG & PB0) && (state == state6)) {
        pb_pressed = 1;  // Set flag for main loop
    }



    // Clear interrupt flags and exit LPM0
    P1IFG &= ~(PB0 + PB1);  // Clear both PB interrupt flags
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
                if (DataFromPC[0] == 'r') { 
                    flash_state = Flash_Reading;
                    read_stage = Read_FileSelect;
                    state = state7;  // Set state7 for read mode
                    display_update_req = 1;  // Request initial display update
                    j = 0; 
                }
                else if (DataFromPC[0] == 'e') { 
                    flash_state = Flash_Executing; 
                    execute_stage = Execute_FileSelect;
                    state = state9;  // Set state9 for execute mode
                    display_update_req = 1;  // Request initial display update
                    j = 0; 
                }
                else if (DataFromPC[0] == 'w') { flash_state = Flash_Writing; write_stage = Write_WaitName; j = 0; }
                else if (DataFromPC[0] == '8') { flash_state = Flash_SelectOp; j = 0; Main = detecor_sel;}
                else {j = 0;}
                break;

            case Flash_Reading:
                // Placeholder: upon newline, return to selector
                if (DataFromPC[j-1] == RX_EOF_CHAR) { flash_state = Flash_SelectOp; j = 0; }
                if (DataFromPC[0] == '8') { flash_state = Flash_SelectOp; j = 0; Main = Flash;}
                break;

            case Flash_Executing:
                // Handle acknowledgment from PC for servo operations
                if (DataFromPC[j-1] == RX_EOF_CHAR) { 
                    // Check if this is an acknowledgment message
                    if (DataFromPC[0] == 'a' && DataFromPC[1] == 'c' && DataFromPC[2] == 'k') {
                        waitready = 1;  // Set the acknowledgment flag
                    }
                    j = 0; 
                }
                if (DataFromPC[0] == '8' || DataFromPC[0] == '5') {
                    exit_flag = 1;
                    //flash_state = Flash_SelectOp;
                    j = 0; Main = Flash;
                }
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
                                Main = Flash;
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



    /*
    switch(lpm_mode){
    case mode0: LPM0_EXIT; break;
    case mode1: LPM1_EXIT; break;
    case mode2: LPM2_EXIT; break;
    case mode3: LPM3_EXIT; break;
    case mode4: LPM4_EXIT; break;
    }
    */
    LPM0_EXIT;
}


// =================== TIMER FUNCTIONS ===================

// Configure Timer A0 with given counter value
void TIMER_A0_config(unsigned int counter) {
    TACCR0 = counter;
    TACCTL0 = CCIE;                            // Enable Timer A0 CCR0 interrupt
    TA0CTL = TASSEL_2 + MC_1 + ID_3;          // SMCLK, Up mode, /8 divider
    TA0CTL |= TACLR;                          // Clear timer
}

// Delay function using Timer A0
void timer_delay_ms(unsigned int ms) {
    unsigned int num_of_halfSec = ms / 500;    // Number of 500ms intervals
    unsigned int remaining_ms = ms % 500;      // Remaining milliseconds
    
    // Handle 500ms intervals
    while(num_of_halfSec--) {
        TIMER_A0_config(HALF_SEC_TICKS);
        __bis_SR_register(LPM0_bits + GIE);    // Enter LPM0 with interrupts
    }
    
    // Handle remaining time if any
    if (remaining_ms > 0) {
        TIMER_A0_config(MS_TO_TICKS(remaining_ms));
        __bis_SR_register(LPM0_bits + GIE);    // Enter LPM0 with interrupts
    }
}

// Timer A0 interrupt service routine
#pragma vector = TIMER0_A0_VECTOR
__interrupt void Timer_A0_ISR(void) {
    TACCTL0 &= ~CCIE;                         // Disable Timer A0 CCR0 interrupt
    __bic_SR_register_on_exit(LPM0_bits);     // Exit LPM0 on return
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
    exit_flag = 0;
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
    // Configure P2.0 as Timer1_A0 capture input
    P2SEL |= BIT0;          // use P2.0 as TA1.0 CCI0A
    P2DIR &= ~BIT0;         // input
    
    // First stop the timer and clear all settings
    TA1CTL = TACLR;         // Clear timer
    
    // Configure TA1CCR0 for edge capture before enabling the timer
    TA1CCTL0 = CM_3 | CCIS_0 | SCS | CAP | CCIE;  // Both edges, CCIxA, sync, capture mode, enable interrupt
    
    // Make sure CCR1 and CCR2 interrupts are disabled (we're only using CCR0)
    TA1CCTL1 = 0;
    TA1CCTL2 = 0;
    
    // Clear any pending flags
    TA1CTL &= ~TAIFG;       // Clear timer overflow flag
    TA1CCTL0 &= ~CCIFG;     // Clear capture/compare flag
    
    // Finally, start the timer with overflow interrupt enabled
    TA1CTL = TASSEL_2 | MC_2 | TAIE;  // SMCLK, continuous mode, enable overflow interrupt
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
    // Reset state variables for new measurement
    cap_count    = 0;     // No edges detected yet
    measure_done = 0;     // Measurement not complete
    
    // Clear any pending interrupt flags and timer
    TA1CCTL0 &= ~(CCIFG | COV);   // Clear CCR0 interrupt flag and overflow flag
    TA1CTL   &= ~TAIFG;           // Clear timer overflow flag
    TA1CTL   |= TACLR | TAIE;     // Clear timer counter and ENABLE overflow interrupt
    
    // Send the trigger pulse (10μs minimum according to HC-SR04 datasheet)
    P1OUT |=  BIT7;               // Set trigger pin high
    __delay_cycles(200);          // Hold for ~10μs (at ~20MHz this is ~200 cycles)
    P1OUT &= ~BIT7;               // Set trigger pin low
    
    // Wait for measurement to complete or timeout (with max safety timeout)
    unsigned int safety_counter = 0;
    while (!measure_done && safety_counter < 50000) { // Added safety timeout
        __bis_SR_register(LPM0_bits | GIE);  // Enter low power mode with interrupts enabled

    }
    
    // If we reached the safety counter limit, set measure_done to timeout
    if (safety_counter >= 50000) {
        measure_done = 2;  // Indicate timeout
        diff_ticks = 0;
    }
    
    // Disable the overflow interrupt when done
    TA1CTL &= ~TAIE;
    
    return diff_ticks;  // Return the measured time difference (or 0 for timeout)
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

