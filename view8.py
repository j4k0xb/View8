import argparse
import os
import shutil
from Parser.parse_v8cache import parse_v8cache_file, parse_disassembled_file
from Simplify.global_scope_replace import replace_global_scope


def disassemble(in_file, input_is_disassembled, disassembler, keep_disasm, out_file):
    out_name = 'disasm.tmp'
    view8_dir = os.path.dirname(os.path.abspath(__file__))

    if input_is_disassembled:
        out_name = in_file
    else:
        # Disassemble the file
        parse_v8cache_file(in_file, out_name, view8_dir, disassembler)

    if keep_disasm and not input_is_disassembled:
        # Preserve the raw disassembly next to the output file, e.g.
        # "out.js" -> "out.disasm.txt". Useful for register-level analysis
        # and for re-running with --disassembled (skips the binary step).
        disasm_path = os.path.splitext(out_file)[0] + '.disasm.txt'
        shutil.copyfile(out_name, disasm_path)
        print(f"Disassembly saved to {disasm_path}.")

    return parse_disassembled_file(out_name)


def decompile(all_functions):
    # Decompile
    print(f"Decompiling {len(all_functions)} functions.")
    for name in list(all_functions)[::-1]:
        all_functions[name].decompile()
    # replace_global_scope(all_functions)


def export_to_file(out_name, all_functions, format_list):
    print(f"Exporting to file {out_name}.")
    with open(out_name, "w", encoding="utf8", errors="replace") as f:
        for function_name in list(all_functions)[::-1]:
            f.write(all_functions[function_name].export(export_v8code="v8_opcode" in format_list, export_translated="translated" in format_list, export_decompiled="decompiled" in format_list))


def main():
    parser = argparse.ArgumentParser(description="View8: V8 cache decompiler.")
    parser.add_argument('input_file', help="The input file name.")
    parser.add_argument('output_file', help="The output file name.")
    parser.add_argument('--path', '-p', help="Path to disassembler binary.", default=None)
    parser.add_argument('--disassembled', '-d', action='store_true', help="Indicate if the input file is already disassembled.")
    parser.add_argument('--keep-disassembly', '-k', action='store_true',
                        help="Also save the raw disassembly (register-level bytecode "
                             "with constant pools) as <output>.disasm.txt. The saved "
                             "file can be re-fed via --disassembled.")
    parser.add_argument('--export_format', '-e', nargs='+', choices=['v8_opcode', 'translated', 'decompiled'],
                        help="Specify the export format(s). Options are 'v8_opcode', 'translated', and 'decompiled'. Multiple options can be combined.",
                        default=['decompiled'])

    args = parser.parse_args()

    if not os.path.isfile(args.input_file):
        raise FileNotFoundError(f"The input file {args.input_file} does not exist.")

    all_func = disassemble(args.input_file, args.disassembled, args.path,
                           args.keep_disassembly, args.output_file)
    decompile(all_func)
    export_to_file(args.output_file, all_func, args.export_format)
    print(f"Done.")


if __name__ == "__main__":
    main()
