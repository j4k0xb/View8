import { CodeSerializer } from "./functions/CodeSerializer.js";
import { ScriptIterator } from "./functions/ScriptIterator.js";
import { SharedFunctionInfo } from "./functions/SharedFunctionInfo.js";

const std_cout = Process.mainModule
  .enumerateSymbols()
  .find((symbol) => symbol.name.includes("cout@@GLIBCXX"))!.address;

Interceptor.attach(CodeSerializer.FinalizeDeserializationPtr, {
  onEnter(args) {
    // Ignore disassembler.js and a bunch of other node built-in modules
    if (!isCachedDataScript(this.context)) return;

    const isolate = args[0];
    const script = new SharedFunctionInfo(args[1]).script();
    const scriptIterator = new ScriptIterator(isolate, script);

    for (const sfi of scriptIterator) {
      sfi.SharedFunctionInfoPrint(std_cout);
      sfi.GetActiveByteCodeArray().Disassemble(std_cout);
    }
  },
});

function isCachedDataScript(context: CpuContext) {
  const backtrace = Thread.backtrace(context, Backtracer.ACCURATE);
  return backtrace.some((address) =>
    DebugSymbol.fromAddress(address).name?.includes(
      "GetSharedFunctionInfoForScriptWithCachedData"
    )
  );
}
