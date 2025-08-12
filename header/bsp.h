#ifndef _bsp_H_
#define _bsp_H_

#include  <msp430g2553.h>          // MSP430x2xx
//#include  <msp430xG46x.h>  // MSP430x4xx


#define   debounceVal      20000



// LCDs abstraction
#define LCD_DATA_WRITE     P1OUT
#define LCD_DATA_DIR       P1DIR
#define LCD_DATA_READ      P1IN
#define LCD_DATA_SEL       P1SEL
#define LCD_CTL_SEL        P2SEL


//   Buzzer abstraction
#define BuzzPortSel        P2SEL
#define BuzzPortDir        P2DIR
#define BuzzPortOut        P2OUT



// PushButtons abstraction
#define PBsArrPort	       P2IN
#define PBsArrIntPend	   P2IFG
#define PBsArrIntEn	       P2IE
#define PBsArrIntEdgeSel   P2IES
#define PBsArrPortSel      P2SEL
#define PBsArrPortDir      P2DIR
#define PBsArrPortOut      P2OUT
//#define PB0                0x01   // P1.0
#define PB1                BIT0     // P2.0
//#define PB2                0x04  // P1.2
//#define PB3                0x08  // P2.0

#define TXLED BIT0
#define RXLED BIT6
#define TXD BIT2
#define RXD BIT1


#define GeneratorPortSel    P2SEL
#define GeneratorPortDir    P2DIR
#define Capture             0x10


extern void GPIOconfig(void);
extern void StopAllTimers(void);
extern void UART_init(void);
extern void TIMER_A1_config(void);



#endif



