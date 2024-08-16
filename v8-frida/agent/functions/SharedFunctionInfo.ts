export const SharedFunctionInfo = {
  /**
   * ```cpp
   * void SharedFunctionInfoPrint(std::ostream& os)
   * ```
   */
  SharedFunctionInfoPrint: new NativeFunction(
    Module.getExportByName(
      null,
      "_ZN2v88internal18SharedFunctionInfo23SharedFunctionInfoPrintERSo"
      // "_ZN2v88internal33TorqueGeneratedSharedFunctionInfoINS0_18SharedFunctionInfoENS0_10HeapObjectEE23SharedFunctionInfoPrintERSo"
    ),
    "void",
    [
      "pointer", // this
      "pointer", // os
    ]
  ),
  /**
   * ```cpp
   * std::unique_ptr<char[]> DebugNameCStr() const
   * ```
   */
  DebugNameCStr: new NativeFunction(
    Module.getExportByName(
      null,
      "_ZNK2v88internal18SharedFunctionInfo13DebugNameCStrEv"
    ),
    "pointer",
    [
      "pointer", // char** output
      "pointer", // this
    ]
  ),
  /**
   * ```cpp
   * inline BytecodeArray GetActiveBytecodeArray()
   * ```
   */
  GetActiveByteCodeArray: new NativeFunction(
    Module.getExportByName(
      null,
      "_ZNK2v88internal18SharedFunctionInfo22GetActiveBytecodeArrayEv"
    ),
    "pointer",
    [
      "pointer", // this
    ]
  ),
};
