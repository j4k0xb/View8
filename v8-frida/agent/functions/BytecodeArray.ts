export const BytecodeArray = {
  /**
   * ```cpp
   * void BytecodeArrayPrint(std::ostream& os)
   * ```
   */
  BytecodeArrayPrint: new NativeFunction(
    Module.getExportByName(
      null,
      "_ZN2v88internal13BytecodeArray18BytecodeArrayPrintERSo"
    ),
    "void",
    [
      "pointer", // this
      "pointer", // os
    ]
  ),
  /**
   * ```cpp
   * void Disassemble(std::ostream& os)
   * ```
   */
  Disassemble: new NativeFunction(
    Module.getExportByName(
      null,
      "_ZN2v88internal13BytecodeArray11DisassembleERSo"
    ),
    "void",
    [
      "pointer", // this
      "pointer", // os
    ]
  ),
};
