from Parser.shared_function_info import SharedFunctionInfo, CodeLine
from parse import parse
import re

all_functions = {}
repeat_last_line = False


def set_repeat_line_flag(flag):
    global repeat_last_line
    repeat_last_line = flag


def get_next_line(file):
    # 使用 latin-1 编码读取，保留所有原始字节（包括 0x80-0xFF）
    with open(file, encoding='latin-1', newline='') as f:
        content = f.read()
    for line in content.split('\n'):
        line = line.strip()
        if not line:
            continue
        yield line
        if repeat_last_line:
            set_repeat_line_flag(False)
            yield line
    yield None


def parse_array(lines, func_name):
    if "Start " not in (line := next(lines)):
        raise Exception(f"Error got line \"{line}\" not Start Array")
    const_list = parse_const_array(lines, func_name)
    array_literal = "[" + ", ".join(const_list) + "]"
    while "End " not in (line := next(lines)):
        pass
    if (line := next(lines)) != ">":
        set_repeat_line_flag(True)
    return array_literal


def parse_object(lines, func_name):
    line = next(lines)
    if "Start " not in line:
        # Newer v8 prints an object header line before the Start marker.
        if "ObjectBoilerplateDescription" in line:
            line = next(lines)
        if "Start " not in line:
            raise Exception(f"Error got line \"{line}\" not Start Object")
    const_list = iter(parse_const_array(lines, func_name)[1:])
    object_literal = "{" + ", ".join([f"{key}: {value}" for key, value in zip(const_list, const_list)]) + "}"
    while "End " not in (line := next(lines)):
        pass
    return object_literal


def parse_bytecode_line(line):
    match = re.search(r"^[^@]+@ +(\d+) : ((?:[0-9a-fA-F]{2} )+) *(.+)$", line)
    if match:
        offset, opcode, inst = match.groups()
        # Decode \uXXXX / \xHHHH escapes in inline operands (e.g. string
        # constants) so non-ASCII (Chinese etc.) shows as real characters.
        inst = unescape_x_escape_to_unicode(inst)
        return CodeLine(opcode=opcode, line=int(offset), inst=inst)
    raise ValueError(f"Invalid bytecode line format: {line}")


def parse_bytecode(line, lines):
    code_list = []
    while " @ " in line:
        code_list.append(parse_bytecode_line(line))
        line = next(lines)
    set_repeat_line_flag(True)
    return code_list

def unescape_x_escape_to_unicode(value: str):
    r"""
    解码 V8 反汇编输出的字符串。
    处理两种格式：
    1. \xHHHH - Unicode 码点转义 (如 \x4e0b = 下)
    2. 原始二进制字节 - 替换为 � (V8 反汇编器的 bug 导致的错误字节)
    """
    import re

    try:
        # 把 \xHHHH 格式转换为 \uHHHH
        def replace_escape(match):
            return r'\u' + match.group(1)

        value = re.sub(r'\\x([0-9a-fA-F]{4})', replace_escape, value)

        # 编码为 latin-1 然后解码 unicode_escape
        result = value.encode('latin-1').decode('unicode_escape')

        # 替换无效字符：
        # 1. Latin-1 范围内的无效字符 (U+0080-U+00FF) - 来自原始二进制字节
        # 2. 控制字符 (U+0000-U+001F)，除了常用的空白字符
        def replace_invalid_char(match):
            return '�'

        # 替换 U+0080-U+00FF 和 U+0000-U+001F (除了 tab, newline)
        # 注意：\r (0x0d) 在 V8 反汇编输出中是错误字节，也需要替换
        # 换行/回车/制表符 -> JS 转义序列，保证输出字符串仍是单行且可读
        # (例如 PEM 证书里的换行、多行文本)
        result = result.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        result = re.sub(r'[\u0000-\u001f\u0080-\u00ff]', replace_invalid_char, result)

        return result
    except Exception as e:
        return value

def _looks_structural(line):
    """判断一行是否像"结构性内容"（新的常量条目或反汇编段落标记），
    而不是某个跨行字符串的正文延续。用于在拼接跨行 <String> 时及时停止。"""
    if re.match(r"^\d+(?:-\d+)?:\s", line):
        return True
    if re.match(r"^0x[0-9a-fA-F]+\s*@", line):  # 字节码行
        return True
    for kw in ("Constant pool", "Handler Table", "Source Position Table",
               "End ", "Start ", "Parameter count", "Register count",
               "Frame size", "Bytecode age", "- length:", "- map:",
               "Slot #", "SharedFunctionInfo", "FixedArray",
               "ObjectBoilerplate", "ArrayBoilerplate", "FeedbackMetadata"):
        if kw in line:
            return True
    return False


def parse_const_line(lines, func_name):
    var_line = next(lines)
    if var_line is None:
        return -1, ""
    match = re.search(r"^(\d+(?:\-\d+)?):\s(0x[0-9a-fA-F]+\s)?(.+)", var_line)
    if not match:
        # Format drift (e.g. multi-line operand tails): keep the raw text.
        return -1, var_line

    idx_range, address, value = match.groups()
    var_idx = int(idx_range.split('-')[-1]) + 1

    if not address:
        return var_idx, value
    if value == "<null>":
        return var_idx, "null"
    if value.startswith("<String"):
        # u# (unicode) 字符串的内容可能包含原始换行符 (0x0A)，反汇编器会原样输出，
        # 导致一个 <String ...> 描述符被拆到多个物理行（甚至漏掉闭合的 '>')。
        # 仅当后续行"不像结构性内容"时才拼接；一旦遇到新常量条目或段落标记，
        # 就把该行放回（repeat）并停止——宁可截断该字符串，也不要吞掉后续内容导致整体失配。
        if not value.endswith(">"):
            for _ in range(64):  # 安全上限，防止异常输入导致死循环
                nxt = next(lines)
                if nxt is None:
                    break
                if _looks_structural(nxt):
                    set_repeat_line_flag(True)  # 把 nxt 放回，交给下一个消费者
                    break
                value += "\n" + nxt
                if value.endswith(">"):
                    break
        value = value.split("#", 1)[-1].rstrip('> ').replace('"', '\\"')
        value = unescape_x_escape_to_unicode(value)
        return var_idx, f'"{value}"'
    if value.startswith("<SharedFunctionInfo"):
        value = value.split(" ", 1)[-1].rstrip('> ') if " " in value else ""
        try:
            return var_idx, parse_shared_function_info(lines, value, func_name)
        except (ValueError, StopIteration):
            return var_idx, f'"unparsed:{value}"'
    if value.startswith("<ArrayBoilerplateDescription") or value.startswith("<FixedArray"):
        try:
            return var_idx, parse_array(lines, func_name)
        except (ValueError, StopIteration, Exception):
            return var_idx, "[]"
    if value.startswith("<ObjectBoilerplateDescription"):
        try:
            return var_idx, parse_object(lines, func_name)
        except (ValueError, StopIteration, Exception):
            return var_idx, "{}"
    if value.startswith("<Odd Oddball"):
        return var_idx, "null"
    if value.startswith("<BigInt"):
        return var_idx, parse("<BigInt {}>", value)[0] + "n"
    return var_idx, value.rstrip('>').split(" ", 1)[-1]


def parse_const_array(lines, func_name):
    while "- length:" not in (line := next(lines)):
        pass
    size = int(parse("- length:{}", line)[0])
    if not size:
        return []

    while not (line := next(lines)).startswith("0"):
        pass
    set_repeat_line_flag(True)

    value = ""
    next_idx = 0
    const_list = []

    for idx in range(size):
        if next_idx != idx:
            const_list.append(value)
            continue
        next_idx, value = parse_const_line(lines, func_name)
        if next_idx == -1:
            # Desync: stop consuming; pad the remainder.
            const_list.extend([""] * (size - idx))
            break
        const_list.append(value)

    return const_list


def parse_const_pool(line, lines, func_name):
    if "size = 0" in line:
        return []
    return parse_const_array(lines, func_name)


def parse_exception_table_line(line):
    from_, to_, key, _ = parse("({},{})  -> {} ({}", line)
    return int(key), [int(from_), int(to_)]


def parse_handler_table(line, lines):
    if "size = 0" in line:
        return {}
    exception_table = {}
    next(lines)
    while " -> " in (line := next(lines)):
        key, value = parse_exception_table_line(line)
        exception_table[key] = value
    set_repeat_line_flag(True)
    return exception_table


def parse_parameter_count(line):
    return int(parse("Parameter count {}", line)[0])


def parse_register_count(line):
    return int(parse("Register count {}", line)[0])


def parse_start_position(line):
    return parse("- start position: {}", line)[0]


def parse_shared_function_info(lines, name, declarer=None):
    sfi = SharedFunctionInfo()
    sfi.declarer = declarer
    sfi.name = 'func_unknown'
    while (line := next(lines)) not in ("End SharedFunctionInfo", None):
        # Nested objects printed inside operand output (e.g. full
        # SharedFunctionInfo blocks after CreateClosure operands) - recurse.
        if line == "Start SharedFunctionInfo":
            parse_shared_function_info(lines, None, declarer=sfi.name)
            continue
        if line == "Start FixedArray":
            try:
                parse_array(lines, sfi.name)
            except (ValueError, StopIteration, Exception):
                pass
            continue
        if line == "Start ObjectBoilerplateDescription":
            try:
                parse_object(lines, sfi.name)
            except (ValueError, StopIteration, Exception):
                pass
            continue
        if line in ("Start BytecodeArray", "End BytecodeArray"):
            continue
        if "- kind: " in line:
            sfi.kind = parse("- kind: {}", line)[0]
        if "- trusted_function_data: " in line and "BytecodeArray" in line:
            sfi.has_bytecode = True
        if "- start position: " in line:
            start_position = parse_start_position(line)
            sfi.name = f'func_{(name or "unknown")}_{start_position}'
        if "Parameter count" in line:
            sfi.argument_count = parse_parameter_count(line)
        elif "Register count" in line:
            sfi.register_count = parse_register_count(line)
        elif "Constant pool" in line:
            sfi.const_pool = parse_const_pool(line, lines, sfi.name)
        elif "Handler Table" in line:
            sfi.exception_table = parse_handler_table(line, lines)
        elif "@    0 : " in line:
            sfi.code = parse_bytecode(line, lines)

    all_functions[sfi.name] = sfi

    if not sfi.is_fully_parsed():
        if any(v is not None for v in (sfi.code, sfi.const_pool)):
            raise ValueError(f"Incomplete parsing of function: {sfi.name}")
        # Uncompiled (lazy) function: fill in placeholders so downstream
        # stages can skip it gracefully.
        sfi.code = []
        sfi.const_pool = []
        sfi.exception_table = {}
        if sfi.argument_count is None: sfi.argument_count = 0
        if sfi.register_count is None: sfi.register_count = 0

    return sfi.name


def parse_file(file="test.txt"):
    lines = get_next_line(file)
    while next(lines) != "Start SharedFunctionInfo":
        pass

    try:
        parse_shared_function_info(lines, "start")
    except StopIteration:
        # Truncated tail (late disassembler crash): keep what was parsed.
        pass
    return all_functions




def _block_lines(block):
    """Line iterator with repeat support over a pre-split block."""
    state = {"lines": list(block), "i": 0, "repeat": False}

    def gen():
        while True:
            if state["i"] >= len(state["lines"]):
                yield None
                continue
            yield state["lines"][state["i"]]
            if not state["repeat"]:
                state["i"] += 1
            state["repeat"] = False

    return gen(), state


def _set_repeat_for(state):
    def setter(_value=True):
        state["repeat"] = True
    return setter


def _split_blocks(lines):
    """Split the disassembly into SharedFunctionInfo blocks, tracking nesting.

    Returns a list of (parent_index, block_lines). Blocks appear in file
    order; a nested block's parent is the enclosing block.
    """
    results = []  # (parent_idx, start_line_idx, end_line_idx)
    stack = []    # indices into results
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line == "Start SharedFunctionInfo":
            parent = stack[-1] if stack else None
            idx = len(results)
            results.append([parent, i, None])
            if stack:
                # rewrite parent end later; children terminate before parent
                pass
            stack.append(idx)
            i += 1
            continue
        if line == "End SharedFunctionInfo":
            if stack:
                idx = stack.pop()
                results[idx][2] = i
            i += 1
            continue
        i += 1
    out = []
    for parent, start, end in results:
        if end is None:
            end = n - 1
        # Strip nested markers from the block content: children are parsed
        # separately; keep only this function's own lines.
        body = []
        j = start + 1
        depth = 0
        while j < end:
            l = lines[j]
            if l == "Start SharedFunctionInfo":
                depth += 1
            elif l == "End SharedFunctionInfo":
                depth -= 1
            elif depth == 0:
                body.append(l.strip())
            j += 1
        out.append((parent, body))
    return out


def parse_file_v15(file="test.txt"):
    """Block-based parser for disassembly produced by newer v8 versions
    (SharedFunctionInfo blocks nest inside operand output)."""
    raw = []
    with open(file, encoding="utf-8", errors="replace") as f:
        raw = f.read().splitlines()

    blocks = _split_blocks(raw)
    global set_repeat_line_flag
    parsed = []  # indices align with blocks
    for parent_idx, body in blocks:
        gen, state = _block_lines(body)
        # per-block repeat flag
        orig_flag = set_repeat_line_flag
        sfi = SharedFunctionInfo()
        declarer = parsed[parent_idx].name if parent_idx is not None and parent_idx < len(parsed) else None
        sfi.declarer = declarer
        sfi.name = 'func_unknown'
        depth_guard = [0]
        try:
            _parse_sfi_body(sfi, gen, state)
        except Exception as e:
            import sys as _sys
            print(f"block-parse-failed @{sfi.name}: {type(e).__name__}: {e}", file=_sys.stderr)
            # Ensure placeholders even when the block failed midway.
            if sfi.code is None: sfi.code = []
            if sfi.const_pool is None: sfi.const_pool = []
            if sfi.exception_table is None: sfi.exception_table = {}
            if sfi.argument_count is None: sfi.argument_count = 0
            if sfi.register_count is None: sfi.register_count = 0
        if sfi.name not in all_functions:
            all_functions[sfi.name] = sfi
        parsed.append(sfi)
    return all_functions


def _parse_sfi_body(sfi, lines, state):
    import Parser.sfi_file_parser as _self
    # local repeat handling
    def local_set_repeat(val=True):
        state["repeat"] = True
    global set_repeat_line_flag
    old = set_repeat_line_flag
    set_repeat_line_flag = local_set_repeat
    try:
        while (line := next(lines)) not in ("End SharedFunctionInfo", None):
            stripped = line.strip()
            if "- kind: " in stripped:
                sfi.kind = _self.parse("- kind: {}", stripped)[0]
            if "- trusted_function_data: " in stripped and "BytecodeArray" in stripped:
                sfi.has_bytecode = True
            if "- name: " in stripped and "#" in stripped:
                nm = stripped.split("#", 1)[1].rstrip(">").strip()
                if nm:
                    sfi.debug_name = nm
            if "- start position: " in stripped:
                start_position = _self.parse("- start position: {}", stripped)[0]
                base = getattr(sfi, "debug_name", None) or "unknown"
                sfi.name = f'func_{base}_{start_position}'
            if "Parameter count" in line:
                sfi.argument_count = _self.parse_parameter_count(line)
            elif "Register count" in line:
                sfi.register_count = _self.parse_register_count(line)
            elif "Constant pool" in line:
                sfi.const_pool = _self.parse_const_pool(line, lines, sfi.name)
            elif "Handler Table" in line:
                sfi.exception_table = _self.parse_handler_table(line, lines)
            elif re.search(r"@ +\d+ : ", line):
                if sfi.code is None:
                    sfi.code = []
                sfi.code.extend(_self.parse_bytecode(line, lines))
            elif line == "Start BytecodeArray" or line == "End BytecodeArray":
                continue
        # Always fill placeholders: partial blocks must not break downstream.
        sfi.code = sfi.code or []
        if sfi.const_pool is None:
            sfi.const_pool = []
        if sfi.exception_table is None:
            sfi.exception_table = {}
        if sfi.argument_count is None:
            sfi.argument_count = 0
        if sfi.register_count is None:
            sfi.register_count = 0
    finally:
        set_repeat_line_flag = old


if __name__ == '__main__':
    parse_file()
