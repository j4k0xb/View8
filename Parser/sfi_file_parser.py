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
    if "Start " not in (line := next(lines)):
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
    match = re.search(r"^(\d+(?:\-\d+)?):\s(0x[0-9a-fA-F]+\s)?(.+)", var_line)
    if not match:
        raise ValueError(f"Invalid constant line format: {var_line} {lines} {func_name}")

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
        return var_idx, parse_shared_function_info(lines, value, func_name)
    if value.startswith("<ArrayBoilerplateDescription") or value.startswith("<FixedArray"):
        return var_idx, parse_array(lines, func_name)
    if value.startswith("<ObjectBoilerplateDescription"):
        return var_idx, parse_object(lines, func_name)
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
        if "- kind: " in line:
            sfi.kind = parse("- kind: {}", line)[0]
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
        raise ValueError(f"Incomplete parsing of function: {sfi.name}")

    return sfi.name


def parse_file(file="test.txt"):
    lines = get_next_line(file)
    while next(lines) != "Start SharedFunctionInfo":
        pass

    parse_shared_function_info(lines, "start")
    return all_functions


if __name__ == '__main__':
    parse_file()
