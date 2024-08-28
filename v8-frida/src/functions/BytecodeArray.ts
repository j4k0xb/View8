export class BytecodeArray {
  constructor(public handle: NativePointer) {}

  /**
   * @param os std::ostream&
   */
  BytecodeArrayPrint(os: NativePointer): void {
    BytecodeArrayPrint(this.handle, os);
  }

  /**
   * @param os std::ostream&
   */
  Disassemble(os: NativePointer): void {
    Disassemble(this.handle, os);
  }
}

const BytecodeArrayPrint = new NativeFunction(
  DebugSymbol.getFunctionByName(
    "_ZN2v88internal13BytecodeArray18BytecodeArrayPrintERSo"
  ),
  "void",
  [
    "pointer", // this
    "pointer", // std::ostream& os
  ]
);
console.log("BytecodeArray::BytecodeArrayPrint", BytecodeArrayPrint);

const Disassemble = new NativeFunction(
  DebugSymbol.getFunctionByName(
    "_ZN2v88internal13BytecodeArray11DisassembleERSo"
  ),
  "void",
  [
    "pointer", // this
    "pointer", // std::ostream& os
  ]
);
console.log("BytecodeArray::Disassemble", Disassemble);
