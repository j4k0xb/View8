import re
import struct


def hex_char_decode(match: re.Match[str]) -> str:
    ch = match.group(1)
    ch = int(ch, 16)
    return struct.pack('B', ch).decode('latin-1')


def uni_char_decode(match: re.Match[str]) -> str:
    ch = match.group(1)
    ch = int(ch, 16)
    return struct.pack('<H', ch).decode('UTF-16LE')


def fix_strings_encoding(all_functions):
    hex_char = r'\\x([0-9a-f]{2})'
    uni_char = r'\\u\{([0-9a-f]{4})\}'

    for func in all_functions.values():
        for line_obj in func.code:
            line = line_obj.decompiled
            line = re.sub(hex_char, hex_char_decode, line)
            line = re.sub(uni_char, uni_char_decode, line)
            line_obj.decompiled = line
