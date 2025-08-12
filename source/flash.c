#include  "../header/flash.h"    // private library - flash layer
#include  "../header/halGPIO.h"    // private library - halGPIO layer
#include  "string.h"

//-----------------------------------------------------------------------------
//           FLASH driver
//-----------------------------------------------------------------------------
#define FLASH_SEGMENT_ADDR 0xF000
#define FLASH_SEGMENT_SIZE 512
#define FLASH_SEGMENT_MASK (~(FLASH_SEGMENT_SIZE - 1u))
#define TEMP_BUFFER_SIZE 64

Files file;
char* current_write_positions[10];  // Track current write position for each file


void ScriptData(void)
{
    file.file_size[file.num_of_files - 1] = strlen(file_content) - 1;

}

void copy_seg_flash(void)
{
    // Backward compatibility: write last file using file_content and stored size
    copy_seg_flash_for_index(file.num_of_files - 1, file_content, (unsigned int)file.file_size[file.num_of_files - 1]);
}

void copy_seg_flash_for_index(short idx, const char* buf, unsigned int len)
{
    char *current_write_pos;                        // Current write position
    unsigned int k;
    
    if (idx < 0 || idx >= 10) return;
    
    // Get current write position, or start at file beginning if first write
    if (current_write_positions[idx] == 0) {
        // First write - do segment setup
        char* segment_start;
        char temp_buffer[TEMP_BUFFER_SIZE];
        unsigned int chunk;
        
        current_write_positions[idx] = file.file_ptr[idx];  // Start at file beginning
        
        // Calculate segment start address (align to segment boundary)
        segment_start = (char*)((unsigned int)current_write_positions[idx] & FLASH_SEGMENT_MASK);
        
        if(idx ==0){
            // Erase the entire segment first
            FCTL1 = FWKEY + ERASE;                          // Set Erase bit
            FCTL3 = FWKEY;                                  // Clear Lock bit
            *segment_start = 0;                             // Dummy write to erase Flash segment
            FCTL1 = FWKEY;                                  // Clear WRT bit
            FCTL3 = FWKEY + LOCK;                           // Set LOCK bit
        }
    }
    
    current_write_pos = current_write_positions[idx];
    
    // Write data directly to flash
    FCTL1 = FWKEY + WRT;
    FCTL3 = FWKEY;// Set WRT bit for write operation
    
    for (k = 0; k < len; k++) {
        if (buf[k] != 0x0A && buf[k] != 0x0D) {
            *current_write_pos++ = buf[k];
        }
    }
    
    FCTL1 = FWKEY;                                  // Clear WRT bit
    FCTL3 = FWKEY + LOCK;                           // Set LOCK bit
    
    // Update current write position for next chunk
    current_write_positions[idx] = current_write_pos;
}

void set_next_file_ptr(short idx)
{
    char* base_addr = (char*)(FLASH_SEGMENT_ADDR);  // Start at beginning of flash
    unsigned int offset = 0;
    short i;
    unsigned int segment_size = FLASH_SEGMENT_SIZE;  // Flash segment size
    
    // Calculate offset by summing all previous file sizes
    for (i = 0; i < idx; i++) {
        offset += (unsigned int)file.file_size[i];
    }
    
    // Calculate the proposed address
    char* proposed_addr = base_addr + offset;
    
    // Check if this file would overlap into the next segment
    char* current_segment_start = (char*)((unsigned int)proposed_addr & FLASH_SEGMENT_MASK);
    unsigned int offset_in_segment = (unsigned int)proposed_addr - (unsigned int)current_segment_start;
    
    // If file would exceed current segment, move to next segment
    if (offset_in_segment + file.file_size[idx] > segment_size) {
        // Move to start of next segment
        proposed_addr = current_segment_start + segment_size;
    }
    
    file.file_ptr[idx] = proposed_addr;
}
