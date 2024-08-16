const { ok } = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const v8 = require("node:v8");
const { brotliDecompressSync } = require("node:zlib");

v8.setFlagsFromString("--no-lazy");

if (Number.parseInt(process.versions.node, 10) >= 12) {
  v8.setFlagsFromString("--no-flush-bytecode");
}

const MAGIC_NUMBER = Buffer.from([0xde, 0xc0]);
const ZERO_LENGTH_EXTERNAL_REFERENCE_TABLE = Buffer.alloc(2);

function generateScript(cachedData, filename) {
  if (!isBufferV8Bytecode(cachedData)) {
    cachedData = brotliDecompressSync(cachedData);

    ok(isBufferV8Bytecode(cachedData), "Invalid bytecode buffer");
  }

  fixBytecode(cachedData);

  const length = readSourceHash(cachedData);

  let dummyCode = "";

  if (length > 1) {
    dummyCode = '"' + "\u200b".repeat(length - 2) + '"'; // "\u200b" Zero width space
  }

  const script = new vm.Script(dummyCode, { cachedData, filename });

  if (script.cachedDataRejected) {
    throw new Error("Invalid or incompatible cached data (cachedDataRejected)");
  }

  return script;
}

function isBufferV8Bytecode(buffer) {
  return (
    Buffer.isBuffer(buffer) &&
    !buffer.subarray(0, 2).equals(ZERO_LENGTH_EXTERNAL_REFERENCE_TABLE) &&
    buffer.subarray(2, 4).equals(MAGIC_NUMBER)
  );
}

const compileCode = function (javascriptCode) {
  const script = new vm.Script(javascriptCode, {
    produceCachedData: true,
  });

  let bytecodeBuffer =
    script.createCachedData && script.createCachedData.call
      ? script.createCachedData()
      : script.cachedData;

  return bytecodeBuffer;
};

const fixBytecode = function (bytecodeBuffer) {
  const dummyBytecode = compileCode('"ಠ_ಠ"');
  const version = parseFloat(process.version.slice(1, 5));

  if (
    process.version.startsWith("v8.8") ||
    process.version.startsWith("v8.9")
  ) {
    // Node is v8.8.x or v8.9.x
    dummyBytecode.subarray(16, 20).copy(bytecodeBuffer, 16);
    dummyBytecode.subarray(20, 24).copy(bytecodeBuffer, 20);
  } else if (version >= 12 && version <= 21) {
    dummyBytecode.subarray(12, 16).copy(bytecodeBuffer, 12);
  } else {
    dummyBytecode.subarray(12, 16).copy(bytecodeBuffer, 12);
    dummyBytecode.subarray(16, 20).copy(bytecodeBuffer, 16);
  }
};

const readSourceHash = function (bytecodeBuffer) {
  if (
    process.version.startsWith("v8.8") ||
    process.version.startsWith("v8.9")
  ) {
    // Node is v8.8.x or v8.9.x
    return bytecodeBuffer
      .subarray(12, 16)
      .reduce(
        (sum, number, power) => (sum += number * Math.pow(256, power)),
        0
      );
  } else {
    return bytecodeBuffer
      .subarray(8, 12)
      .reduce(
        (sum, number, power) => (sum += number * Math.pow(256, power)),
        0
      );
  }
};

const bytecodeBuffer = fs.readFileSync("test.jsc");
generateScript(bytecodeBuffer);
