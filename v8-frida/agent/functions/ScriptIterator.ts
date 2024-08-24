import { SharedFunctionInfo } from "./SharedFunctionInfo.js";

export class ScriptIterator {
  handle: NativePointer;

  constructor(isolate: NativePointer, script: NativePointer) {
    this.handle = Memory.alloc(Process.pointerSize);
    this.handle.writePointer(ScriptIterator.new(this.handle, isolate, script));
  }

  [Symbol.iterator](): Iterator<SharedFunctionInfo> {
    return {
      next: () => {
        const sfi = ScriptIterator.Next(this.handle);
        if (sfi.isNull()) {
          return { done: true, value: null };
        }
        const handle = Memory.alloc(Process.pointerSize);
        handle.writePointer(sfi);
        return { done: false, value: new SharedFunctionInfo(handle) };
      },
    };
  }

  /**
   * ```cpp
   * SharedFunctionInfo::ScriptIterator::ScriptIterator(Isolate* isolate, Script* script)
   * ```
   */
  private static new = new NativeFunction(
    DebugSymbol.getFunctionByName(
      "_ZN2v88internal18SharedFunctionInfo14ScriptIteratorC1EPNS0_7IsolateENS0_6ScriptE"
    ),
    "pointer",
    [
      "pointer", // destination
      "pointer", // isolate
      "pointer", // script
    ]
  );

  /**
   * ```cpp
   * SharedFunctionInfo SharedFunctionInfo::ScriptIterator::Next()
   * ```
   */
  private static Next = new NativeFunction(
    DebugSymbol.getFunctionByName(
      "_ZN2v88internal18SharedFunctionInfo14ScriptIterator4NextEv"
    ),
    "pointer",
    [
      "pointer", // this
    ]
  );
}
