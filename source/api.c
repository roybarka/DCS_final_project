// =================== INCLUDES ===================
#include "../header/api.h"
#include "../header/flash.h"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>

// =================== STATIC/OUTPUT HELPERS ===================
static char newline[] = " \r\n";
static char dst_char[5];
static char deg_char[7];
static char Light_char[5];

// =================== OUTPUT HELPER FUNCTIONS ===================
void send_meas(unsigned int meas, unsigned int iter) {
    ltoa(iter, deg_char);
    ltoa(meas, dst_char);
    ser_output(deg_char);
    ser_output(":");
    ser_output(dst_char);
    ser_output(newline);
}

void send_two_meas(unsigned int iter, unsigned int avg_meas, unsigned int dist) {
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

// =================== FSM / HIGH-LEVEL ROUTINES ===================

// Objects Detector
// TA0 in up-mode with TA0CCR0 = 20000 @ SMCLK=1MHz -> 20 ms period (50 Hz).
// Using TA0.1 (P1.6) with OUTMOD_7 (reset/set):
// pulse width [ticks] = TACCR1; 1 tick = 1us => 600..2400 ticks = 0.6..2.4 ms
// We map deg [0..180] to CCR1 = 600 + 10*deg.
void Objects_Detector(void) {
    init_trigger_gpio();
    init_echo_capture();
    __bis_SR_register(GIE);
    while(state==state1){
        int iter, iter_meas, dist;
        deg = 600;
        TACCR1 = deg;
        TACCTL1 = OUTMOD_7;
        TACTL = TASSEL_2 | MC_1;
        TA1CTL = TASSEL_2 | MC_2;
        __delay_cycles(300000);
        for (iter = 0; iter < 180 && state==state1; iter++) {
            IE2 &= UCA0RXIE;
            deg += 10;
            TACCR1 = deg;
            __delay_cycles(20000);
            for (iter_meas = 0; iter_meas < 7; iter_meas++) {
                dist = send_trigger_pulse();
                send_meas(dist,iter);
                __delay_cycles(3000);
            }
        }
    }
}

// Telemeter
void Telemeter(void) {
    telemetr_config();
    telemeter_deg_update();
    __delay_cycles(1000000);
    while(state==state2 & change_deg==0) {
        int dist;
        IE2 &= UCA0RXIE;
        dist = send_trigger_pulse();
        send_meas(dist,deg);
        IE2 |= UCA0RXIE;
        __delay_cycles(10000);
    }
}

// Light Detector
void Light_Detector(void) {
    while(state==state3){
        int iter;
        unsigned int avg_meas;
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

// Object and Light Detector
void Object_and_Light_Detector(void) {
    init_trigger_gpio();
    init_echo_capture();
    __bis_SR_register(GIE);
    while(state==state4){
        int iter;
        unsigned int avg_meas;
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

void LDRcalibrate(void) {
    if (pb_pressed) {
        unsigned int measurement = LDRmeas();
        save_LDR(measurement, measureCounter);
        measureCounter++;
        if(measureCounter == 10){
            measureCounter = 0;
        }
        pb_pressed = 0;  // Clear the flag
    }
}


void testlcd(){
    lcd_init();
    lcd_clear();
    lcd_puts("this is a test");
}

// =================== FILE READING FUNCTIONS ===================

// Display function for file selection mode
static void display_file_info(void) {
    lcd_clear();
     volatile char idx_buf[2] = {0};  volatile char name_buf[11] = {0}; volatile char type_buf[4] = {0};
    ltoa(current_file_idx, idx_buf);
    strcpy(name_buf, file.file_name[current_file_idx]);
    strcpy(type_buf, (file.file_type[current_file_idx] == text) ? "txt" : "scr");
    lcd_puts(idx_buf); lcd_puts(") "); lcd_puts(name_buf);
    lcd_new_line;
    lcd_puts("file type: "); lcd_puts(type_buf);
}

// Display function for file content mode
static void display_file_content(void) {
    lcd_clear();
    volatile char display_buf1[16] = {0};  // First line buffer
    volatile char display_buf2[16] = {0};  // Second line buffer
    char *file_start = file.file_ptr[current_file_idx];
    int remaining = file.file_size[current_file_idx] - current_read_pos;
    
    // Copy first line (up to 15 chars)
    int bytes_to_read = (remaining < 15) ? remaining : 15;
    memcpy(display_buf1, file_start + current_read_pos, bytes_to_read);
    
    // Copy second line if there's more content
    remaining -= bytes_to_read;
    if (remaining > 0) {
        bytes_to_read = (remaining < 15) ? remaining : 15;
        memcpy(display_buf2, file_start + current_read_pos + 15, bytes_to_read);
    }
    // Display both lines
    lcd_puts(display_buf1);
    lcd_new_line;
    lcd_puts(display_buf2);
}

// Main read function called from state7
void ReadFiles(void) {
    if (display_update_req) {
        if (read_stage == Read_FileSelect) {
            display_file_info();
        } else if (read_stage == Read_FileDisplay) {
            display_file_content();
        }
        display_update_req = 0;  // Clear the update flag
    }
}
