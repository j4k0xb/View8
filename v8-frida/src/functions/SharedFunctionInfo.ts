import { BytecodeArray } from "./BytecodeArray.js";

export class SharedFunctionInfo {
  constructor(public handle: NativePointer) {}

  /**
   * @param os std::ostream&
   */
  SharedFunctionInfoPrint(os: NativePointer): void {
    SharedFunctionInfoPrint(this.handle, os);
  }

  /**
   * @returns HeapObject
   */
  script(): NativePointer {
    return script(this.handle);
  }

  GetActiveByteCodeArray(): BytecodeArray {
    const bca = GetActiveByteCodeArray(this.handle);
    const handle = Memory.alloc(Process.pointerSize);
    handle.writePointer(bca);
    return new BytecodeArray(handle);
  }
}

const SharedFunctionInfoPrint = new NativeFunction(
  DebugSymbol.getFunctionByName(
    "_ZN2v88internal18SharedFunctionInfo23SharedFunctionInfoPrintERSo"
  ),
  "void",
  [
    "pointer", // this
    "pointer", // std::ostream& os
  ]
);
console.log(
  "SharedFunctionInfo::SharedFunctionInfoPrint",
  SharedFunctionInfoPrint
);

const script = new NativeFunction(
  DebugSymbol.findFunctionsMatching(
    "*SharedFunctionInfo*scriptENS0*constprop*"
  )[0] ?? // Node v18, v20
    DebugSymbol.getFunctionByName(
      "_ZNK2v88internal18SharedFunctionInfo6scriptEv"
    ), // Node v16
  "pointer", // HeapObject
  [
    "pointer", // this
  ]
);
console.log("SharedFunctionInfo::script", script);

const GetActiveByteCodeArray = new NativeFunction(
  DebugSymbol.getFunctionByName(
    "_ZNK2v88internal18SharedFunctionInfo22GetActiveBytecodeArrayEv"
  ),
  "pointer", // BytecodeArray
  [
    "pointer", // this
  ]
);
console.log(
  "SharedFunctionInfo::GetActiveByteCodeArray",
  GetActiveByteCodeArray
);
