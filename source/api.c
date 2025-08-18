// =================== INCLUDES ===================
#include "../header/api.h"
#include "../header/flash.h"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>

// Number of repeated LDR samples to average during calibration (mode 6)
#define CAL_SAMPLES 15

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

// Progress messages for LDR calibration (mode 6)
static void send_calib_progress(unsigned int step /*1..10*/) {
    // Format: "6:<step>" + newline
    ltoa(step, dst_char);
    ser_output("6:");
    ser_output(dst_char);
    ser_output(newline);
}

static void send_calib_done(void) {
    // Format: "6:DONE" + newline
    ser_output("6:DONE");
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
            deg = 600 + (10 * iter);
            TACCR1 = deg;
            TACTL = TASSEL_2 | MC_1;
            __delay_cycles(25000);
            TACTL = TASSEL_2 | MC_0;
            for (iter_meas = 0; iter_meas < 10; iter_meas++) {
                IE2 &= UCA0RXIE;
                dist = send_trigger_pulse();
                send_meas(dist,iter);
                IE2 |= UCA0RXIE;
                __delay_cycles(13000);
            }
        }
    }
}

// Telemeter
void Telemeter(void) {
    telemetr_config();
    telemeter_deg_update();
    int dist;
    __delay_cycles(1000000);
    while(state==state2 & change_deg==0) {
        IE2 &= UCA0RXIE;
        dist = send_trigger_pulse();
        send_meas(dist,deg);
        IE2 |= UCA0RXIE;
        __delay_cycles(15000);
    }
}

// Light Detector (mode 3): scan angles 0-179, move servo, sample LDR, send angle:value
void Light_Detector(void) {
    init_trigger_gpio();
    deg = 600;
    TACCR1 = deg;
    TACCTL1 = OUTMOD_7;
    TACTL = TASSEL_2 | MC_1;
    int sample;
    int iter, ldr_val;
    __delay_cycles(300000);
    while(state==state3){
        deg = 600;
        TACCR1 = deg;
        __delay_cycles(50000);
        for (iter = 0; iter < 180 && state==state3; iter++) {
            deg = 600 + (10 * iter);
            TACCR1 = deg;
            __delay_cycles(5000);
            // Take multiple samples per angle to allow robust aggregation on host
            for (sample = 0; sample < 15; sample++) {
            ldr_val = LDRmeas();
            send_meas(ldr_val, iter); // send as angle:value
            __delay_cycles(1000);
            }
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
        // Capture and store current calibration measurement
        unsigned int step = measureCounter + 1; // 1..10 for user display
        // Take multiple consecutive samples and average them to reduce noise
        unsigned long sum = 0UL; // avoid overflow while accumulating
        int k;
        for (k = 0; k < CAL_SAMPLES; k++) {
            sum += (unsigned long)LDRmeas();
            __delay_cycles(1000);  // short gap between samples
        }
        unsigned int avg = (unsigned int)((sum + (CAL_SAMPLES / 2)) / CAL_SAMPLES); // rounded mean
        save_LDR(avg, measureCounter);

        // Notify host about progress (which step was recorded)
        send_calib_progress(step);

    // Advance counter and, if finished, notify completion
        measureCounter++;
        if (measureCounter >= 10) {
            send_calib_done();
            measureCounter = 0;
        }

        pb_pressed = 0;  // Clear the flag
    } else {
        TACCR1 = 1500;
        TACCTL1 = OUTMOD_7;
        TACTL = TASSEL_2 | MC_1;
        __delay_cycles(1000000);
        TACTL = TASSEL_2 | MC_0;

    }
}

// =================== LDR CALIBRATION SENDER ===================
void send_LDR_calibration_values(void) {
    unsigned int* ldr_calib_addr = (unsigned int*)0x1000;
    unsigned int calib_value;
    int i;
    for (i = 0; i < 10; i++) {
        calib_value = ldr_calib_addr[i];
        send_meas(calib_value, i); // Reuse send_meas to send value and index
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
