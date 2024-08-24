import { CodeSerializer } from "./functions/CodeSerializer.js";
import { ScriptIterator } from "./functions/ScriptIterator.js";
import { SharedFunctionInfo } from "./functions/SharedFunctionInfo.js";

const std_cout = Process.mainModule
  .enumerateSymbols()
  .find((symbol) => symbol.name.includes("cout@@GLIBCXX"))!.address;

Interceptor.attach(CodeSerializer.FinalizeDeserializationPtr, {
  onEnter(args) {
    const isolate = args[0];
    const script = new SharedFunctionInfo(args[1]).script();
    const scriptIterator = new ScriptIterator(isolate, script);

    for (const sfi of scriptIterator) {
      if (!sfi.HasBytecodeArray()) continue;

      sfi.SharedFunctionInfoPrint(std_cout);
      const bytecodeArray = sfi.GetActiveByteCodeArray();
      bytecodeArray.Disassemble(std_cout);
    }
  },
});
