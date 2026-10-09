"""Extract a read-only-reference remap table from a --trace-deserialization log.

Modern V8 runtimes (Node/Electron) extend the read-only heap at startup with
thousands of internalized strings. Code caches produced by such a runtime
reference those objects by (chunk, offset). A View8 v8dasm build only matches
the *static* part of the runtime's read-only heap; references into the
runtime-dependent diverged region cannot be resolved locally.

This tool parses a trace produced by the ORIGINAL runtime consuming the very
same .jsc file:

    ELECTRON_RUN_AS_NODE=1 ./electron --trace-deserialization -e "
        const vm=require('vm'),fs=require('fs');
        new vm.Script('dummy', {cachedData: fs.readFileSync('in.jsc'), filename:'x'});" > trace.log

and writes a TSV map of (chunk, offset) -> string content, restricted to the
diverged region (page >= 6 here; adjust if your runtime differs).
"""

import re
import sys

# Read-only pages whose content depends on the runtime build/config and which
# a plain V8 build cannot reproduce. Adjust per target runtime if needed.
def is_diverged(chunk, offset):
    if chunk >= 7:
        return True
    if chunk == 6 and offset >= 0x20198:
        return True
    return False


def main():
    trace_path, out_path = sys.argv[1], sys.argv[2]
    pat = re.compile(r'^\s*\d* ReadOnlyHeapRef \[(\d+), (\d+)\] : \S+ <(.*)>$')
    seen = {}
    for line in open(trace_path, errors="replace"):
        m = pat.match(line)
        if not m:
            continue
        chunk, offset, desc = int(m.group(1)), int(m.group(2)), m.group(3)
        if not is_diverged(chunk, offset):
            continue
        if desc.startswith("String["):
            # 'String[N]: #content' - content runs to end of line.
            content = desc.split(": #", 1)[1] if ": #" in desc else ""
            seen[(chunk, offset)] = ("s", content)
        else:
            seen[(chunk, offset)] = ("o", desc)
    with open(out_path, "w", encoding="utf-8") as f:
        for (chunk, offset), (kind, content) in sorted(seen.items()):
            content = content.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")
            f.write(f"{chunk}\t{offset}\t{kind}\t{content}\n")
    print(f"wrote {len(seen)} diverged ro-refs to {out_path}")


if __name__ == "__main__":
    main()
