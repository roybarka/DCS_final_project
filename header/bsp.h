#ifndef _bsp_H_
#define _bsp_H_

#include <msp430g2553.h> // MSP430x2xx

// =================== GENERAL ===================
#define debounceVal 20000

// =================== TIMER CONSTANTS ===================
#define CLK_FREQ 1000000  // 1MHz
#define CLK_DIV 8         // Timer divider
#define MS_TO_TICKS(ms) ((CLK_FREQ / CLK_DIV / 1000) * ms)
#define HALF_SEC_TICKS MS_TO_TICKS(500)

// =================== PUSH BUTTONS ===================
#define PB0 BIT0    // Push Button 0 is P1.0
#define PB1 BIT5    // Push Button 1 is P1.5

// =================== LCD ABSTRACTION ===================
#define LCD_DATA_WRITE P2OUT
#define LCD_DATA_DIR   P2DIR
#define LCD_DATA_READ  P2IN
#define LCD_DATA_SEL   P2SEL
#define LCD_CTL_SEL    P2SEL

// =================== PUSHBUTTONS ABSTRACTION ===================
#define PBsArrPort      P2IN
#define PBsArrIntPend   P2IFG
#define PBsArrIntEn     P2IE
#define PBsArrIntEdgeSel P2IES
#define PBsArrPortSel   P2SEL
#define PBsArrPortDir   P2DIR
#define PBsArrPortOut   P2OUT

// =================== UART/LED ABSTRACTION ===================
#define TXLED BIT0
#define RXLED BIT6
#define TXD   BIT2
#define RXD   BIT1

#endif



extern void PBconfig(void);
extern void GPIOconfig(void);
extern void StopAllTimers(void);
extern void UART_init(void);
extern void TIMER_A1_config(void);







