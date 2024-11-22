import { SharedFunctionInfo } from "./SharedFunctionInfo.js";

export class ScriptIterator {
  handle = Memory.alloc(Process.pointerSize);

  constructor(isolate: NativePointer, script: NativePointer) {
    $constructor(this.handle, isolate, script);
  }

  [Symbol.iterator](): Iterator<SharedFunctionInfo> {
    return {
      next: () => {
        const sfi = Next(this.handle);
        if (sfi.isNull()) {
          return { done: true, value: null };
        }
        const handle = Memory.alloc(Process.pointerSize);
        handle.writePointer(sfi);
        return { done: false, value: new SharedFunctionInfo(handle) };
      },
    };
  }
}

const $constructor = new NativeFunction(
  DebugSymbol.getFunctionByName(
    "_ZN2v88internal18SharedFunctionInfo14ScriptIteratorC1EPNS0_7IsolateENS0_6ScriptE"
  ),
  "pointer", // SharedFunctionInfo::ScriptIterator
  [
    "pointer", // SharedFunctionInfo::ScriptIterator destination
    "pointer", // Isolate* isolate
    "pointer", // Script* script
  ]
);
console.log("ScriptIterator", $constructor);

const Next = new NativeFunction(
  DebugSymbol.getFunctionByName(
    "_ZN2v88internal18SharedFunctionInfo14ScriptIterator4NextEv"
  ),
  "pointer", // SharedFunctionInfo
  [
    "pointer", // this
  ]
);
console.log("ScriptIterator::Next", Next);
