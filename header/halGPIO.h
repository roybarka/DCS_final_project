#ifndef _halGPIO_H_
#define _halGPIO_H_

#include "../header/bsp.h"
#include "../header/main.h"

// =================== GLOBALS USED ACROSS MODULES ===================
extern enum FSMstate state;
extern enum SYSmode lpm_mode;
extern char delay_array[5];
extern int change_deg;
extern volatile int temp[2];
extern volatile float diff;
extern volatile unsigned int deg;
extern volatile unsigned int deg_duty_cycle;

// =================== PUBLIC HAL/API ===================
void sysConfig(void);
void telemetr_config(void);
void telemeter_deg_update(void);
void put_on_lcd(char*, unsigned int);
unsigned int send_trigger_pulse(void);
void ser_output(char *);
unsigned int LDRmeas(void);
void init_echo_capture(void);
void init_trigger_gpio(void);

// --- LCD configuration & API (unchanged) ---
#ifdef CHECKBUSY
#define LCD_WAIT lcd_check_busy()
#else
#define LCD_WAIT DelayMs(5)
#endif

#endif

#define LCD_EN(a)        (!a ? (P2OUT&=~0x20) : (P2OUT|=0x20))   // P2.5
#define LCD_EN_DIR(a)    (!a ? (P2DIR&=~0x20) : (P2DIR|=0x20))
#define LCD_RS(a)        (!a ? (P2OUT&=~0x40) : (P2OUT|=0x40))   // P2.6
#define LCD_RS_DIR(a)    (!a ? (P2DIR&=~0x40) : (P2DIR|=0x40))
#define LCD_RW(a)        (!a ? (P2OUT&=~0x80) : (P2OUT|=0x80))   // P2.7
#define LCD_RW_DIR(a)    (!a ? (P2DIR&=~0x80) : (P2DIR|=0x80))

#define LCD_DATA_OFFSET  0x04

#define FOURBIT_MODE     0x0
#define EIGHTBIT_MODE    0x1
#define LCD_MODE         FOURBIT_MODE

#define OUTPUT_PIN       1
#define INPUT_PIN        0
#define OUTPUT_DATA      (LCD_MODE ? 0xFF : (0x0F << LCD_DATA_OFFSET))
#define INPUT_DATA       0x00

#define LCD_STROBE_READ(value)  do { \
  LCD_EN(1); asm("nop"); asm("nop"); \
  value = LCD_DATA_READ; \
  LCD_EN(0); } while(0)

#define lcd_cursor(x)       lcd_cmd(((x)&0x7F)|0x80)
#define lcd_clear()         lcd_cmd(0x01)
#define lcd_putchar(x)      lcd_data(x)
#define lcd_goto(x)         lcd_cmd(0x80+(x))
#define lcd_cursor_right()  lcd_cmd(0x14)
#define lcd_cursor_left()   lcd_cmd(0x10)
#define lcd_display_shift() lcd_cmd(0x1C)
#define lcd_home()          lcd_cmd(0x02)
#define cursor_off          lcd_cmd(0x0C)
#define cursor_on           lcd_cmd(0x0F)
#define lcd_function_set    lcd_cmd(0x3C) // 8bit,two lines,5x10 dots
#define lcd_new_line        lcd_cmd(0xC0)

extern void lcd_cmd(unsigned char);
extern void lcd_data(unsigned char);
extern void lcd_puts(const char *s);
extern void lcd_init(void);
extern void lcd_strobe(void);
extern void DelayMs(unsigned int);
extern void DelayUs(unsigned int);
extern void clear_string(char*);


