import { BytecodeArray } from "./BytecodeArray.js";

export class SharedFunctionInfo {
  handle: NativePointer;

  constructor(handle: NativePointer) {
    this.handle = handle;
  }

  SharedFunctionInfoPrint(os: NativePointer): void {
    SharedFunctionInfo.SharedFunctionInfoPrint(this.handle, os);
  }

  DebugNameCStr(): string {
    const output = Memory.alloc(Process.pointerSize);
    SharedFunctionInfo.DebugNameCStr(output, this.handle);
    return output.readPointer().readCString()!;
  }

  script(): NativePointer {
    return SharedFunctionInfo.script(this.handle);
  }

  HasBytecodeArray(): boolean {
    return SharedFunctionInfo.HasBytecodeArray(this.handle) === 1;
  }

  GetActiveByteCodeArray(): BytecodeArray {
    const bca = SharedFunctionInfo.GetActiveByteCodeArray(this.handle);
    const handle = Memory.alloc(Process.pointerSize);
    handle.writePointer(bca);
    return new BytecodeArray(handle);
  }

  /**
   * ```cpp
   * void SharedFunctionInfoPrint(std::ostream& os)
   * ```
   */
  private static SharedFunctionInfoPrint = new NativeFunction(
    DebugSymbol.getFunctionByName(
      "_ZN2v88internal18SharedFunctionInfo23SharedFunctionInfoPrintERSo"
      // "_ZN2v88internal33TorqueGeneratedSharedFunctionInfoINS0_18SharedFunctionInfoENS0_10HeapObjectEE23SharedFunctionInfoPrintERSo"
    ),
    "void",
    [
      "pointer", // this
      "pointer", // os
    ]
  );

  /**
   * ```cpp
   * std::unique_ptr<char[]> DebugNameCStr() const
   * ```
   */
  private static DebugNameCStr = new NativeFunction(
    DebugSymbol.getFunctionByName(
      "_ZNK2v88internal18SharedFunctionInfo13DebugNameCStrEv"
    ),
    "pointer",
    [
      "pointer", // char** output
      "pointer", // this
    ]
  );

  /**
   * ```cpp
   * Script* script() const
   * ```
   */
  private static script = new NativeFunction(
    DebugSymbol.getFunctionByName(
      "_ZNK2v88internal18SharedFunctionInfo6scriptENS0_16PtrComprCageBaseE.constprop.0"
    ),
    "pointer",
    [
      "pointer", // this
    ]
  );

  /**
   * ```cpp
   * bool HasBytecodeArray()
   * ```
   */
  private static HasBytecodeArray = new NativeFunction(
    DebugSymbol.getFunctionByName(
      "_ZNK2v88internal18SharedFunctionInfo16HasBytecodeArrayENS0_16PtrComprCageBaseE.constprop.0"
    ),
    "bool",
    [
      "pointer", // this
    ]
  );

  /**
   * ```cpp
   * inline BytecodeArray GetActiveBytecodeArray()
   * ```
   */
  private static GetActiveByteCodeArray = new NativeFunction(
    DebugSymbol.getFunctionByName(
      "_ZNK2v88internal18SharedFunctionInfo22GetActiveBytecodeArrayEv"
    ),
    "pointer",
    [
      "pointer", // this
    ]
  );
}
