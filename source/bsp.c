#include "../header/bsp.h"

//-----------------------------------------------------------------------------  
//           GPIO configuration
//-----------------------------------------------------------------------------
void GPIOconfig(void){
  // Stop watchdog (password + hold)
  WDTCTL = WDTPW | WDTHOLD;  // TI: writes to WDTCTL require WDTPW; WDTHOLD stops WDT. :contentReference[oaicite:6]{index=6}

  // --- Servo PWM on P1.6 (TA0.1) ---
  P1DIR  |= BIT6;            // P1.6 as output
  P1SEL  |= BIT6;            // select peripheral function
  P1SEL2 &= ~BIT6;           // ensure TA0.1 function (not USCI). Datasheet shows P1.6-TA0.1. :contentReference[oaicite:7]{index=7}
  TACCR0  = 20000;           // 20ms period at 1 MHz (used by your servo code later)

  // --- Trigger on P1.7 (GPIO) ---
  P1DIR  |= BIT7;
  P1OUT  &= ~BIT7;
  P1SEL  &= ~BIT7;           // force GPIO
  P1SEL2 &= ~BIT7;

  // --- Echo on P2.0 (TA1.0 capture input CCI0A) ---
  P2DIR  &= ~BIT0;           // input
  P2SEL  |=  BIT0;           // select TA1.0 on P2.0
  P2SEL2 &= ~BIT0;

  //LCD config
  P2SEL  &= ~(BIT1|BIT2|BIT3|BIT4|BIT5|BIT6|BIT7);
  P2SEL2 &= ~(BIT1|BIT2|BIT3|BIT4|BIT5|BIT6|BIT7);
  P2OUT  &= ~(BIT1|BIT2|BIT3|BIT4|BIT5|BIT6|BIT7);
  P2DIR  |=  (BIT1|BIT2|BIT3|BIT4|BIT5|BIT6|BIT7);

  // --- Timer1_A capture for Echo (both edges, sync, interrupt) ---
  TA1CTL   = TASSEL_2 | MC_2 | TACLR;            // SMCLK, continuous
  TA1CCTL0 = CM_3 | CCIS_0 | SCS | CAP | CCIE;   // CCR0 now
  TA1CCTL1 = 0;                                   // optional: ensure CCR1 is off
}

void PBconfig(void) {
    // Configure both PB0 and PB1 as inputs with pull-ups and interrupts
    P1DIR &= ~(PB0 + PB1);      // Set as inputs
    P1SEL &= ~(PB0 + PB1);      // GPIO function
    P1SEL2 &= ~(PB0 + PB1);     // GPIO function
    P1REN |= (PB0 + PB1);       // Enable pull-up/down resistors
    P1OUT |= (PB0 + PB1);       // Set as pull-up
    P1IES |= (PB0 + PB1);       // Interrupt on falling edge
    P1IE |= (PB0 + PB1);        // Enable interrupts
    P1IFG &= ~(PB0 + PB1);      // Clear interrupt flags
}

//-------------------------------------------------------------------------------------
//            Stop All Timers
//-------------------------------------------------------------------------------------
void StopAllTimers(void){
  TA0CTL = MC_0;  // halt Timer_A0 (MC=0: stop), per TAxCTL.MC bits. :contentReference[oaicite:16]{index=16}
  TA1CTL = MC_0;  // halt Timer_A1
}


//-------------------------------------------------------------------------------------
//                              UART init
//-------------------------------------------------------------------------------------
void UART_init(void){
  // DCO @ 1MHz using factory constants (trap if erased)
  if (CALBC1_1MHZ == 0xFF) { while(1); }                 // :contentReference[oaicite:24]{index=24}
  DCOCTL  = 0;
  BCSCTL1 = CALBC1_1MHZ;                                 // DCO range to 1MHz
  DCOCTL  = CALDCO_1MHZ;                                 // DCO step + modulation

  // USCI_A0 pins on P1.1 (RXD) / P1.2 (TXD)
  P1SEL  |= BIT1 | BIT2;
  P1SEL2 |= BIT1 | BIT2;                                 // datasheet maps P1.1/P1.2 to UCA0RXD/TXD. :contentReference[oaicite:25]{index=25}

  UCA0CTL1 |= UCSWRST;                                   // hold USCI in reset (TI recommended) :contentReference[oaicite:26]{index=26}
  UCA0CTL1 |= UCSSEL_2;                                  // SMCLK is the UART clock. :contentReference[oaicite:27]{index=27}
  UCA0BR0    = 104;                                      // 1,000,000 / 9600 = 104.166...
  UCA0BR1    = 0x00;
  UCA0MCTL   = UCBRS0;                                   // UCBRSx=1 fractional modulation. :contentReference[oaicite:28]{index=28}
  UCA0CTL1  &= ~UCSWRST;                                 // release for operation :contentReference[oaicite:29]{index=29}
}
