#ifndef _main_H_
#define _main_H_

// =================== ENUMS FOR FSM STATE AND SYSTEM MODE ===================
enum FSMstate { state1, state2, state3, state4, state5, state6, state7, state8, state9 };
enum SYSmode  { mode0, mode1, mode2, mode3, mode4 };

// Top-level main states
enum main_states{detecor_sel, Tele_get_deg, Flash};

// Flash operation selector (second FSM)
enum flash_states{Flash_SelectOp, Flash_Reading, Flash_Executing, Flash_Writing};

// Writing sub-stages
enum write_stages{Write_WaitName, Write_WaitType, Write_WaitSize, Write_WaitContent};

// Reading sub-stages
enum read_stages{Read_FileSelect, Read_FileDisplay};

// Legacy/aux enums (kept, extended)
enum StatusReceive{Name,Type,Size,Content};
enum FileType{script,text};

#endif

















