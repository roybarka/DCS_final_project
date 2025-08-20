#ifndef HEADER_FLASH_H_
#define HEADER_FLASH_H_

#include  <msp430g2553.h>          // MSP430x2xx
#include "../header/main.h"

#define FLASH_SEGMENT_ADDR 0xF000
#define FLASH_SEGMENT_SIZE 512
#define FILES_STRUCT_FLASH_ADDR 0xE000  // Flash address for storing Files struct metadata

extern void ScriptData(void);
extern void SetPtrData(void);
extern void copy_seg_flash(void);
typedef struct Files{
    short num_of_files;
    char file_name[10][11];
    char* file_ptr[10];
    int file_size[10];
    enum FileType file_type[10];


}Files;
extern Files file;
// Write 'len' bytes from 'buf' into flash at file index 'idx'.
extern void copy_seg_flash_for_index(short idx, const char* buf, unsigned int len);
// Calculate and set the next free flash address for file 'idx'
extern void set_next_file_ptr(short idx);
extern void save_LDR(unsigned int measurement, unsigned int counter);
// Track current write position for each file
extern char* current_write_positions[10];
// Flash persistence functions
extern void upload_files_from_flash(void);    // Load Files struct from flash at startup
extern void download_files_to_flash(void);    // Save Files struct to flash after writing
#endif /* HEADER_FLASH_H_ */




