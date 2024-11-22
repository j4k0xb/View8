import { Deserialize } from "./functions/CodeSerializer.js";
import { ScriptIterator } from "./functions/ScriptIterator.js";
import { SharedFunctionInfo } from "./functions/SharedFunctionInfo.js";

const std_cout = Process.mainModule
  .enumerateSymbols()
  .find((symbol) => symbol.name.includes("cout@@GLIBCXX"))!.address;

let isolate = NULL;

Interceptor.attach(Deserialize, {
  onEnter(args) {
    isolate = args[0];
  },
  onLeave(retval) {
    if (!isCachedDataScript(this.context)) return;

    const script = new SharedFunctionInfo(retval).script();
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
      "GetSharedFunctionInfoForScript"
    )
  );
}
