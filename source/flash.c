#include  "../header/flash.h"    // private library - flash layer
#include  "../header/halGPIO.h"    // private library - halGPIO layer
#include  "string.h"

//-----------------------------------------------------------------------------
//           FLASH driver
//-----------------------------------------------------------------------------
#define FLASH_SEGMENT_ADDR 0xF000
#define FLASH_SEGMENT_D 0x1000
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
    /**
 * Writes data to flash memory for a specific file index
 * 
 * This function handles flash memory writes with segment management:
 * 1. Tracks write position for each file
 * 2. Erases flash segments only on first write to that segment
 * 3. Filters out newline characters when writing
 * 
 * @param idx - Index of the file (0-9) to write to
 * @param buf - Buffer containing data to write
 * @param len - Length of data to write
 * @note Uses static segment tracking to optimize segment erasure
 * @note Automatically handles flash control registers for write operations
 */
    char *current_write_pos;                        // Current write position
    unsigned int k;
    
    if (idx < 0 || idx >= 10) return;
    
    // Get current write position, or start at file beginning if first write
    if (current_write_positions[idx] == 0) {
        // First write - do segment setup
        static char* segment_start;
        char* temp_segment_start;
        char temp_buffer[TEMP_BUFFER_SIZE];
        unsigned int chunk;
        
        current_write_positions[idx] = file.file_ptr[idx];  // Start at file beginning
        
        // Calculate segment start address (align to segment boundary)
        temp_segment_start = (char*)((unsigned int)current_write_positions[idx] & FLASH_SEGMENT_MASK);
        
        if(idx == 0 || segment_start != temp_segment_start) {
            // Erase segment if this is first file or a new segment
            segment_start = temp_segment_start;     // Remember this segment
            FCTL1 = FWKEY + ERASE;                 // Set Erase bit
            FCTL3 = FWKEY;                         // Clear Lock bit
            *segment_start = 0;                    // Dummy write to erase Flash segment
            FCTL1 = FWKEY;                         // Clear WRT bit
            FCTL3 = FWKEY + LOCK;                 // Set LOCK bit
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
    /**
 * Calculates and sets the starting flash memory address for the next file
 * 
 * This function manages the flash memory allocation for multiple files:
 * 1. Computes the offset from base address using previous files' sizes
 * 2. Ensures files don't cross segment boundaries (512 byte segments)
 * 3. If a file would cross a segment boundary, it's placed at the start of the next segment
 * 
 * @param idx - Index of the file (0-9) to set its starting address
 * @note Uses FLASH_SEGMENT_ADDR (0xF000) as the base address
 * @note Stores the calculated address in file.file_ptr[idx]
 */
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

void save_LDR(unsigned int measurement, unsigned int counter) {
    char* flash_addr = (char*)(FLASH_SEGMENT_D + 2*counter);

    if (counter == 0) {
        // First time: erase the segment and unlock flash for writing
        FCTL1 = FWKEY + ERASE; // Set Erase bit
        FCTL3 = FWKEY;         // Clear Lock bit
        *flash_addr = 0;       // Dummy write to erase Flash segment
        FCTL1 = FWKEY;         // Clear WRT bit
        FCTL3 = FWKEY + LOCK;  // Set LOCK bit
    }

    // Write measurement to flash
    FCTL1 = FWKEY + WRT; // Enable write
    FCTL3 = FWKEY;       // Clear Lock bit

    // Write measurement as 2 bytes (assuming 16-bit unsigned int)
    flash_addr[0] = (char)(measurement & 0xFF);
    flash_addr[1] = (char)((measurement >> 8) & 0xFF);

    FCTL1 = FWKEY;         // Clear WRT bit
    FCTL3 = FWKEY + LOCK;  // Set LOCK bit
}

void upload_files_from_flash(void) {
    // Read Files struct from flash
    Files* flash_files = (Files*)FILES_STRUCT_FLASH_ADDR;
    
    // Check if flash contains valid data (simple validation)
    if (flash_files->num_of_files <= 10 && flash_files->num_of_files >= 0) {
        // Copy from flash to RAM
        memcpy(&file, flash_files, sizeof(Files));
    } else {
        // Initialize empty file structure
        memset(&file, 0, sizeof(Files));
        file.num_of_files = 0;
    }
}

void download_files_to_flash(void) {
    char* dst;
    char* src;
    int i;
    
    // Erase the flash segment
    FCTL1 = FWKEY + ERASE;
    FCTL3 = FWKEY;
    *(char*)FILES_STRUCT_FLASH_ADDR = 0;  // Dummy write to erase
    
    // Write Files struct to flash
    FCTL1 = FWKEY + WRT;
    FCTL3 = FWKEY;
    
    src = (char*)&file;
    dst = (char*)FILES_STRUCT_FLASH_ADDR;
    
    for (i = 0; i < sizeof(Files); i++) {
        *dst++ = *src++;
    }
    
    FCTL1 = FWKEY;
    FCTL3 = FWKEY + LOCK;
}
