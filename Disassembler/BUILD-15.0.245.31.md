# v8dasm 构建指南：V8 15.0.245.31（Electron 43.x / Node 24）

本文档记录 `Bin/15.0.245.31/` 目录下反汇编器的完整构建过程，涵盖所有
新版 V8 / Electron 目标特有的问题（原 README 未涉及）。

## 背景

Electron / Node 运行时产生的 code cache 与裸 V8 构建的差异有三点：

1. **版本哈希算法变了**：V8 14 起 `Version::Hash()` 改为正序折叠
   （`base::Hasher`，major→minor→build→patch），而 13.x 及之前是逆序折叠。
   Python 版本探测器（`Parser/version_detector.py`）同时实现了两种算法。
2. **构建参数差异**：Electron 会设置额外的 GN 参数
   （`v8_promise_internal_field_count`、`v8_enable_javascript_promise_hooks`、
   `v8_embedder_string` 等），其中最关键的是 `v8_wasm_random_fuzzers = false`
   （官方构建默认关闭，standalone 构建默认开启）。该开关会改变
   `ExternalReferenceTable::kSize`（1734 vs 1735），而 kSize 直接编入 code
   cache 的 magic number；不一致时反序列化会在深处崩溃。
3. **只读堆被运行时扩展**：Node 引导阶段会把约 2 万条字符串内化进额外的
   只读堆页（第 8/9 页），且第 6/7 页的部分内容因构建而异（哈希种子不同、
   每个 builtin 的元数据大小不同）。code cache 通过 (chunk, offset) 引用
   这些对象。

## `Bin/15.0.245.31/` 目录内容

- `v8dasm` —— 反汇编器二进制（已 strip）。
- `hybrid_snapshot.bin` —— 我们自己的启动快照 blob，其只读段拼接了
  运行时快照多出的只读页（8/9 页）。通过环境变量 `V8DASM_SNAPSHOT_BLOB`
  注入。
- `ro_image.bin` —— 运行时快照的只读堆镜像，作为**预言机**使用：
  落在分歧区（第 6 页尾部、第 7 页）的引用直接从该镜像字节解码
  （字符串重建为普通堆字符串；其他对象用 `undefined` 占位）。
  通过环境变量 `V8DASM_RO_IMAGE` 注入。

`Parser/parse_v8cache.py` 会在两个文件与 v8dasm 同目录时自动注入，
无需手动设置环境变量。

## 构建步骤

1. checkout V8 `15.0.245.31`，依次应用：
   - electron v43.5.0 的 13 个 `patches/v8/*.patch`（`git am --3way`）；
   - 本仓库的 `Disassembler/v8.patch`（需手工解冲突：短打印辅助函数已
     移到 `src/diagnostics/objects-printer.cc`；`SharedFunctionInfoPrint`
     里 `GetActiveBytecodeArray` 需要 isolate 参数；须用
     `HasBytecodeArray()` 保护，未编译的懒函数没有字节码）。
2. 针对运行时快照所需的额外补丁（都在 v8 源码树的
   `electron-43-build` 分支上）：
   - `startup-deserializer.cc`：跳过外部引用别名 CHECK（不同构建的
     别名对可能不一致，但流仍需按原样消费）。
   - `deserializer.cc`：根槽位/句柄槽位上的外部引用改为"读取并丢弃"
     （槽位计数为 1，保持流对齐）；`ReadReadOnlyHeapRef` 先查询预言机
     `v8dasm_ro_remap_lookup()`；RO 越界诊断输出。
   - `isolate.cc`：禁用 builtin 的判断同时兼容 entrypoint tag 不匹配的
     情况（替换为 kIllegal）。
   - `string-forwarding-table.cc`：越界的转发索引返回空哈希（共享
     字符串表运行时产生的索引在本进程中不存在）。
   - `string-inl.h`：`TryReportUnreachable` 直接返回 false（字符串分发
     遇到损坏 shape 时回退到空字符串，而不是崩溃）。
   - `string.cc`：打印前做形状校验（`StringShortPrint`、`ToCString` 入口），
     递归校验 cons/thin/sliced 链及只读页边界，损坏字符串打印占位符；
     超长字符串（>4096 字符）截断打印，避免损坏引用产生兆级垃圾输出。
   - `objects-printer.cc`：map 字合法性校验、分歧区地址守卫、
     未编译 SFI 守卫。
3. GN 参数（`out.gn/x64.release/args.gn`）：
   ```ini
   dcheck_always_on = false
   is_component_build = false
   is_debug = false
   target_cpu = "x64"
   use_custom_libcxx = true
   v8_monolithic = true
   v8_use_external_startup_data = false
   v8_static_library = true
   v8_enable_disassembler = true
   v8_enable_object_print = true
   v8_enable_pointer_compression = true
   v8_enable_sandbox = true
   symbol_level = 1
   # 以下来自 electron build/args/all.gn：
   v8_promise_internal_field_count = 1
   v8_embedder_string = "-electron.0"
   v8_enable_snapshot_native_code_counters = false
   v8_enable_javascript_promise_hooks = true
   v8_enable_private_mapping_fork_optimization = true
   # 对齐官方构建（ExternalReferenceTable::kSize = 1734）：
   v8_wasm_random_fuzzers = false
   v8_enable_fuzztest = false
   ```
4. 把 v8dasm 作为 GN 目标构建（手工 clang++ 链接已不可行：monolith 会
   拉入 Rust/LTO 对象）：
   ```gn
   v8_executable("v8dasm") {
     sources = [ "samples/v8dasm.cc" ]
     configs = [ ":internal_config_base" ]
     deps = [ ":v8", ":v8_libbase", ":v8_libplatform" ]
   }
   ```
   `samples/v8dasm.cc` 相比原版的增强：命令行旗标解析、外部快照 blob
   注入、哑外部字符串资源表、RO 镜像预言机加载、崩溃时刷缓冲并以
   退出码 77 结束（保留部分输出）。
5. 从目标 `electron` 二进制提取运行时的快照 blob：扫描 64 字节版本串
   `15.0.245.31-electron.0`（位于 blob 偏移 +16 处），校验头部
   （num_contexts 合理、各段偏移单调），取**只读段最大**的那个 blob
   （是 Node 的，不是 Blink 的）。
6. 制作 `hybrid_snapshot.bin`：保留我们自己的 blob，把运行时快照 RO
   镜像里多出的页记录（`kAllocatePageAt`/`kSegment` 字节码）注入我们
   的 RO 镜像流（插在 `kFinalizeReadOnlySpace` 之前）。
7. 裁剪 `ro_image.bin`：取运行时 blob 从头部到 RO 段结束
   （`startup_offset` + 少量余量）的字节。

## 从目标 App 自己的二进制生成预言机文件

同版本号的 Electron 重编译构建（版本串 / kSize / 版本哈希完全相同）在只读堆
第 6/7 页的布局会因编译产物差异（PGO、clang 等）而不同——code cache 里的
引用按 App 运行时自己的布局生成。用**官方** Electron 的快照做预言机会把
部分引用解码到对象中间，产生乱码常量。因此预言机文件应从 **App 自己的**
运行时二进制提取：

```sh
python3 tools/extract_runtime_blob.py <App的electron二进制> Bin/15.0.245.31/ \
        --our-blob <我们构建的mksnapshot输出> [--version 15.0.245.31-electron.0]
```

自动扫描二进制内的快照 blob（取 RO 段最大的，即 Node 的），生成
`ro_image.bin` 与 `hybrid_snapshot.bin`，与 v8dasm 同目录即自动生效。

## 备注

- `BUILTIN_BLOCK_POSITION` / builtin 的 PGO 配置不影响只读堆布局，
  无需匹配（实测开启后 RO 大小不变）。
- 反汇编器遇到损坏字符串时以退出码 77 结束，但已输出的内容会全部
  刷盘、可用（`parse_v8cache.py` 把 77 视为"成功但有截断警告"）。
- 换其他 Electron 版本时：按同样配方重选 v8 tag 构建，并从对应版本的
  `electron` 二进制重新提取快照 blob，重新生成两个 `.bin` 文件即可。

## 相关文件清单（本仓库内）

| 文件 | 说明 |
|---|---|
| `Bin/15.0.245.31/v8dasm` | 反汇编器（52MB，strip 后） |
| `Bin/15.0.245.31/hybrid_snapshot.bin` | 混合启动快照（RO 段含运行时扩展页） |
| `Bin/15.0.245.31/ro_image.bin` | 运行时 RO 镜像（预言机） |
| `Parser/version_detector.py` | 跨平台版本探测器（新旧两种哈希算法） |
| `Parser/parse_v8cache.py` | 自动注入 blob / 退出码 77 处理 / 版本目录查找 |
| `Parser/sfi_file_parser.py` | `parse_file_v15` 块式解析器（兼容 10.8 与 15.x） |
| `Parser/ro_trace_extract.py` | 从 --trace-deserialization 日志提取 RO 引用对照表（备用方案） |
| `Disassembler/BUILD-15.0.245.31.md` | 本文档 |
