from Translate.translate import translate_bytecode
from Simplify.simplify import simplify_translated_bytecode


class CodeLine:
    def __init__(self, opcode="", line="", inst="", translated="", decompiled=""):
        self.v8_opcode = opcode
        self.line_num = line
        self.v8_instruction = inst
        self.translated = translated
        self.pre_defined = None
        self.decompiled = decompiled
        self.visible = True


class SharedFunctionInfo:
    def __init__(self):
        self.name = None
        self.declarer = None
        self.function_header = None
        self.argument_count = None
        self.register_count = None
        self.code = None
        self.const_pool = None
        self.exception_table = None
        self.kind = None
        self.defined = False

    def is_fully_parsed(self):
        return all(
            value is not None for value in [
                self.argument_count, self.register_count,
                self.const_pool, self.exception_table, self.code
            ]
        )

    def create_function_header(self):
        parameters = ', '.join([f'a{i}' for i in range(int(self.argument_count) - 1)])
        if self.kind == "AsyncFunction":
            return f"async function {self.name}({parameters})"
        elif self.kind == "GeneratorFunction":
            return f"function* {self.name}({parameters})"
        elif self.kind == "AsyncGeneratorFunction":
            return f"async function* {self.name}({parameters})"
        else:
            return f"function {self.name}({parameters})"

    def translate_bytecode(self):
        translate_bytecode(self.name, self.code, self.exception_table)

    def simplify_bytecode(self):
        simplify_translated_bytecode(self, self.code)

    def replace_const_pool(self, nested: bool):
        def unescape(var):
            if var.startswith('"') and var.endswith('"'):
                return var[1:-1].replace('\\\\', '\\')
            else:
                return var

        replacements = {}
        replacements.update({
            f"LiteralConstPool[{idx}]": var for idx, var in enumerate(self.const_pool)
        })
        replacements.update({
            f"ConstPool[{idx}]": unescape(var) for idx, var in enumerate(self.const_pool)
        })
        for line in self.code:
            if not line.visible:
                continue
            for const_id, var in replacements.items():
                if const_id not in line.decompiled:
                    continue
                if nested and var in self.const_functions and not self.const_functions[var].defined:
                    self.const_functions[var].decompile(nested)
                    if line.pre_defined is None:
                        line.pre_defined = []
                    line.pre_defined.append(self.const_functions[var])
                line.decompiled = line.decompiled.replace(const_id, var)

    def decompile(self, nested: bool):
        self.translate_bytecode()
        self.simplify_bytecode()
        self.replace_const_pool(nested)
        self.defined = True

    def export(self, export_v8code=False, export_translated=False, export_decompiled=True, nested=False, nested_level=0, tab_level=0):
        export_padding = (' ' * ((6+50)*export_v8code+60*export_translated)) * nested_level + '\t' * tab_level
        export_func = export_padding + self.create_function_header() + '\n'
        for line in self.code:
            if (not line.visible or not line.decompiled) and not export_v8code and not export_translated:
                continue

            export_line = export_padding
            if export_v8code:
                export_line += f'{line.line_num:<6}'
                export_line += f'{line.v8_instruction:<50}'
            if export_translated:
                export_line += f'{line.translated:<60}'
            if export_decompiled:
                if line.visible:
                    if nested and line.pre_defined:
                        for const_function in line.pre_defined:
                            export_line = const_function.export(export_v8code, export_translated, export_decompiled, nested, nested_level+1, tab_level + line.tab_level) + export_line
                    export_line += '\t' * line.tab_level + f'{line.decompiled}'
            if export_line != export_padding:
                export_func += export_line + '\n'
        return export_func
