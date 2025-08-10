// MSP430G2553 + HC-SR04 (manual trigger)
// Connections (updated):
//   P1.7 -> HC-SR04 TRIG (output, GPIO)    <-- changed from P1.6
//   P2.1 -> HC-SR04 ECHO (input, TA1.1 / CCI1A capture)
//   P1.1/P1.2 -> UART (USCI_A0 RXD/TXD @ 9600 baud)
//
// Timing & math:
//   SMCLK = 1 MHz from factory calibration
//   Timer1_A in continuous mode -> 1 tick = 1 us
//   distance_cm = echo_width_us / 58  (per HC-SR04 datasheet)
//
// Notes:
//   If your module outputs 5V on ECHO, level-shift to protect the MSP430 input.

#include <msp430.h>
#include <stdlib.h>
#include <math.h>

// ---- UART helpers ----
static void ser_output(char *s) {
    while (*s) {
        while (!(IFG2 & UCA0TXIFG));   // TX buffer ready
        UCA0TXBUF = *s++;
    }
}
static void ser_uint(unsigned int v, char *buf) {
    // TI toolchains sometimes want a base arg; use the 2-arg if available.
    // If you get errors, switch to: ltoa(v, buf, 10);
    ltoa(v, buf);
}

// ---- Capture state (shared with ISR) ----
volatile unsigned int t_rise = 0, t_fall = 0;
volatile unsigned int diff_ticks = 0;
volatile unsigned char cap_count = 0;
volatile unsigned char measure_done = 0;

// ---- Prototypes ----
static void init_clock_1MHz(void);
static void init_uart_9600(void);
static void init_trigger_gpio(void);
static void init_echo_capture(void);
static void send_trigger_pulse(void);

int main(void)
{
    WDTCTL = WDTPW | WDTHOLD;            // Stop watchdog

    // Use factory DCO calibration for 1 MHz (trap if missing)
    if (CALBC1_1MHZ == 0xFF) while (1);
    init_clock_1MHz();
    init_uart_9600();
    init_trigger_gpio();
    init_echo_capture();

    __bis_SR_register(GIE);              // Global interrupt enable

    while (1) {
        send_trigger_pulse();            // Trigger -> measure echo -> print distance
        __delay_cycles(70000);           // >=60 ms between pings (HC-SR04 recommendation)
    }
}

// ---- Init functions ----
static void init_clock_1MHz(void)
{
    DCOCTL  = 0;                         // Start from known state
    BCSCTL1 = CALBC1_1MHZ;               // Load factory VCO range for 1 MHz
    DCOCTL  = CALDCO_1MHZ;               // Load factory DCO step for 1 MHz
    // Result: MCLK/SMCLK sourced from DCO = 1 MHz (default after PUC).
}

static void init_uart_9600(void)
{
    // Route P1.1/P1.2 to USCI_A0
    P1SEL  |= BIT1 | BIT2;
    P1SEL2 |= BIT1 | BIT2;

    UCA0CTL1 |= UCSSEL_2;                // BRCLK = SMCLK
    UCA0BR0 = 104;                       // 1,000,000 / 9600 = 104.167
    UCA0BR1 = 0;
    UCA0MCTL = UCBRS0;                   // First-order modulation
    UCA0CTL1 &= ~UCSWRST;                // Release USCI from reset
}

static void init_trigger_gpio(void)
{
    // P1.7 as plain GPIO output (TRIG)  -- select I/O function
    P1SEL  &= ~BIT7;   // GPIO, not peripheral
    P1SEL2 &= ~BIT7;   // GPIO, not secondary function
    P1DIR  |=  BIT7;   // output direction
    P1OUT  &= ~BIT7;   // idle LOW (recommended by most HC-SR04 examples)
}

static void init_echo_capture(void)
{
    // P2.1 -> TA1.1 CCI1A (ECHO input)
    P2SEL |= BIT1;            // select timer function on P2.1
    P2DIR &= ~BIT1;           // input

    // Timer1_A: SMCLK (1 MHz), continuous mode
    TA1CTL = TASSEL_2 | MC_2 | TAIE; // SMCLK, continuous up to 0xFFFF +TAIE: enable overflow interrupt (TAIFG)

    // CCR1 capture on both edges, input = CCI1A, synchronized, interrupt enabled
    TA1CCTL1 = CM_3 | CCIS_0 | SCS | CAP | CCIE;
}

// ---- Single-iteration measurement and print ----
static void send_trigger_pulse(void)
{
    // Prepare capture state
    cap_count    = 0;
    measure_done = 0;
    TA1CCTL1 &= ~(CCIFG | COV);   // clear any pending flag/overflow
    TA1CTL   |= TACLR;            // reset TAR and divider to 0 before starting

    // Emit >=10 us HIGH pulse on TRIG (P1.7)
    P1OUT |=  BIT7;
    __delay_cycles(2000);   // ~12 µs at 1 MHz (meets > 10 µs spec)
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
    // Convert microseconds to centimeters: us/58
    float distance_cm = ((float)diff_ticks) / 58.0f;   // HC-SR04 formula

    // Print "Distance: <int>.<frac> cm"
    char ibuf[8], fbuf[8];
    unsigned int d_int  = (unsigned int)floorf(distance_cm);
    unsigned int d_frac = (unsigned int)floorf((distance_cm - d_int) * 100.0f + 0.5f); // 2 decimals

    ser_output("Distance: ");
    ser_uint(d_int, ibuf);  ser_output(ibuf);
    ser_output(".");
    if (d_frac < 10) ser_output("0");
    ser_uint(d_frac, fbuf); ser_output(fbuf);
    ser_output(" cm\r\n");
}

// ---- Timer1_A1 ISR: service CCR1 captures (both edges) ----
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
