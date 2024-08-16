import { BytecodeArray } from "./functions/BytecodeArray.js";
import { CodeSerializer } from "./functions/CodeSerializer.js";
import { SharedFunctionInfo } from "./functions/SharedFunctionInfo.js";

const std_cout = Process.mainModule
  .enumerateSymbols()
  .find((symbol) => symbol.name.includes("cout@@GLIBCXX"))!.address;

Interceptor.attach(CodeSerializer.FinalizeDeserializationPtr, {
  onEnter(args) {
    const sfiHandle = args[1];
    const bytecodeArray = SharedFunctionInfo.GetActiveByteCodeArray(sfiHandle);
    const bytecodeArrayPtr = Memory.alloc(Process.pointerSize);
    bytecodeArrayPtr.writePointer(bytecodeArray);
    BytecodeArray.Disassemble(bytecodeArrayPtr, std_cout);

    // Works but is an empty string
    // const namePtr = Memory.alloc(Process.pointerSize);
    // console.log(
    //   "FinalizeDeserialization",
    //   JSON.stringify(
    //     SharedFunctionInfo.DebugNameCStr(namePtr, sfiHandle)
    //       .readPointer()
    //       .readCString()
    //   )
    // );
  },
});
