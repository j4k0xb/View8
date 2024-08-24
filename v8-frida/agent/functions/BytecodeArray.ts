export class BytecodeArray {
  handle: NativePointer;

  constructor(handle: NativePointer) {
    this.handle = handle;
  }

  BytecodeArrayPrint(os: NativePointer): void {
    BytecodeArray.BytecodeArrayPrint(this.handle, os);
  }

  Disassemble(os: NativePointer): void {
    BytecodeArray.Disassemble(this.handle, os);
  }

  /**
   * ```cpp
   * void BytecodeArrayPrint(std::ostream& os)
   * ```
   */
  private static BytecodeArrayPrint = new NativeFunction(
    DebugSymbol.getFunctionByName(
      "_ZN2v88internal13BytecodeArray18BytecodeArrayPrintERSo"
    ),
    "void",
    [
      "pointer", // this
      "pointer", // os
    ]
  );

  /**
   * ```cpp
   * void Disassemble(std::ostream& os)
   * ```
   */
  private static Disassemble = new NativeFunction(
    DebugSymbol.getFunctionByName(
      "_ZN2v88internal13BytecodeArray11DisassembleERSo"
    ),
    "void",
    [
      "pointer", // this
      "pointer", // os
    ]
  );
}
