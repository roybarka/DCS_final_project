from __future__ import annotations

import re
from typing import List

# Opcode map per your Script ISA
OPCODES = {
    "inc_lcd":    0x01,  # inc_lcd x
    "dec_lcd":    0x02,  # dec_lcd x
    "rra_lcd":    0x03,  # rra_lcd x (ASCII char or byte)
    "set_delay":  0x04,  # set_delay d (units of 10ms)
    "clear_lcd":  0x05,  # clear_lcd
    "servo_deg":  0x06,  # servo_deg p (0..179)
    "servo_scan": 0x07,  # servo_scan l,r (0..179 each)
    "sleep":      0x08,  # sleep
}

_SPLIT_COMMAS = re.compile(r"[,\s]+")


def _parse_byte(tok: str) -> int:
    """Parse one byte from decimal/hex or a quoted char ('A')."""
    tok = tok.strip()
    if not tok:
        raise ValueError("missing operand")

    # char literal
    if (tok.startswith("'") and tok.endswith("'")) or (tok.startswith('"') and tok.endswith('"')):
        inner = tok[1:-1]
        if len(inner) != 1:
            raise ValueError(f"char literal must be length 1: {tok}")
        return ord(inner)

    # decimal or hex (0x..)
    val = int(tok, 0)
    if not (0 <= val <= 255):
        raise ValueError(f"byte out of range 0..255: {tok}")
    return val


def encode_script_text(text: str) -> bytes:
    """
    Encode high-level script text into opcode bytes.
    - Ignores blank lines and comments starting with '#' or '//'
    - Tokens can be separated by spaces and/or commas
    - Numbers can be decimal or hex (e.g., 0x1E)
    """
    out: List[int] = []
    for ln, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue

        parts = [p for p in _SPLIT_COMMAS.split(line) if p]
        if not parts:
            continue

        name = parts[0].lower()
        if name not in OPCODES:
            raise ValueError(f"line {ln}: unknown instruction '{name}'")

        out.append(OPCODES[name])

        if name in ("inc_lcd", "dec_lcd", "rra_lcd", "set_delay", "servo_deg"):
            if len(parts) != 2:
                raise ValueError(f"line {ln}: '{name}' expects 1 operand")
            out.append(_parse_byte(parts[1]))

        elif name == "servo_scan":
            if len(parts) != 3:
                raise ValueError(f"line {ln}: 'servo_scan' expects 2 operands (l,r)")
            l = _parse_byte(parts[1]); r = _parse_byte(parts[2])
            if not (0 <= l <= 179 and 0 <= r <= 179):
                raise ValueError(f"line {ln}: angles must be 0..179")
            out.extend([l, r])

        elif name in ("clear_lcd", "sleep"):
            if len(parts) != 1:
                raise ValueError(f"line {ln}: '{name}' expects no operands")

    return bytes(out)
