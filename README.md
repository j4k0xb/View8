# View8

`View8` 是一个静态分析工具，将 V8 序列化字节码缓存文件（JSC）反编译为
接近 JavaScript 的可读代码。View8 使用一个打过补丁并重新编译的 V8 二进制
（v8dasm）来完成反汇编，再用 Python 层做翻译与反编译。

原版英文说明保留在 [README.old.md](./README.old.md)。

## 支持的 V8 版本

| V8 版本 | 对应运行时 | 说明 |
|---|---|---|
| `9.4.146.24` | Node 16.x | 官方发布版 |
| `10.2.154.26` | Node 18.x | 官方发布版 |
| `10.8.168.25` | Electron 22.x | 官方发布版 |
| `11.3.244.8` | Node 20.x | 官方发布版 |
| `15.0.245.31` | Electron 43.x / Node 24 | 本仓库自行构建（Linux），见下文 |

> 上游 [suleram/View8](https://github.com/suleram/View8) 目前仅支持到
> 11.3；15.0.245.31 支持为本地扩展，构建方法见
> [Disassembler/BUILD-15.0.245.31.md](./Disassembler/BUILD-15.0.245.31.md)。

## 环境要求

- Python 3.x（纯 Python，无第三方依赖；`parse` 库可选）
- 反汇编器二进制：按版本存放在 `Bin/<v8版本>/` 目录下

## 用法

```sh
# 自动探测版本并在 Bin/<版本>/ 下寻找反汇编器（推荐）
python3 view8.py input.jsc output.js

# 手动指定反汇编器
python3 view8.py input.jsc output.js -p Bin/15.0.245.31/v8dasm

# 输入已是反汇编文本时跳过反汇编步骤
python3 view8.py input.txt output.js --disassembled

# 同时导出 V8 操作码 / 翻译结果 / 反编译代码
python3 view8.py input.jsc output.js -e v8_opcode translated decompiled
```

### 命令行参数

- `input_file`：输入文件（.jsc 或已反汇编文本）
- `output_file`：输出文件
- `--path` / `-p`：手动指定反汇编器路径（缺省时自动探测）
- `--disassembled` / `-d`：输入已是反汇编文本
- `--export_format` / `-e`：导出格式，可选 `v8_opcode`、`translated`、
  `decompiled`，可组合，默认 `decompiled`

## 版本探测

V8 字节码文件的头部存有版本哈希。View8 支持两种探测方式：

1. **Windows**：`Bin/VersionDetector.exe`（仅支持旧版哈希算法）
2. **跨平台 Python 探测器**（`Parser/version_detector.py`）：上面不可用时
   自动回退。同时实现了新旧两种版本哈希算法：
   - 旧算法（≤ V8 13.x）：逆序折叠
   - 新算法（V8 14+）：`base::Hasher` 正序折叠

探测到版本后会自动按 `Bin/<版本>/v8dasm` 查找反汇编器。

其他获取目标 V8 版本的途径：

- <https://j4k0xb.github.io/v8-version-analyzer>
- 有 Node 二进制时：`node -p process.versions.v8`
- 有 Electron 二进制时：
  - Linux/Mac：`ELECTRON_RUN_AS_NODE=1 ./electron -p process.versions.v8`
  - Windows：`set ELECTRON_RUN_AS_NODE=1 && electron.exe -p process.versions.v8`
- 已知 Electron 版本时：查 <https://releases.electronjs.org/releases.json> 的 `v8` 字段
- 已知 Node 版本时：查 <https://nodejs.org/dist/index.json> 的 `v8` 字段

如果暴力匹配不到版本，说明该 V8 被定制过，选择最接近的版本即可。

## 反汇编器目录结构

```
Bin/
├── VersionDetector.exe          # Windows 版本探测器（旧算法）
├── 10.8.168.25/
│   └── v8dasm                   # 10.8 反汇编器
└── 15.0.245.31/
    ├── v8dasm                   # 15.0 反汇编器（Linux）
    ├── hybrid_snapshot.bin      # 混合启动快照（含运行时扩展的只读页）
    └── ro_image.bin             # 运行时只读堆镜像（分歧区预言机）
```

对 Electron 43（V8 15.0）这类新版目标，两个 `.bin` 文件必须与 `v8dasm`
放在同一目录，`view8.py` 会自动通过环境变量注入（`V8DASM_SNAPSHOT_BLOB` /
`V8DASM_RO_IMAGE`），无需手动设置。

> 反汇编器二进制不入库，需要自行构建或获取。15.0 版本的完整构建步骤见
> [Disassembler/BUILD-15.0.245.31.md](./Disassembler/BUILD-15.0.245.31.md)。

## 新版 V8（Electron 运行时）的特殊处理

Electron/Node 运行时产生的 code cache 与裸 V8 构建存在三方面差异，
15.0 反汇编器做了对应处理：

1. **版本哈希算法变更**（V8 14+）：Python 探测器已兼容
2. **构建参数差异**：`v8_wasm_random_fuzzers` 等参数影响外部引用表大小
   （magic number），构建时已按官方配置对齐
3. **只读堆被运行时扩展**：Node 引导会把约 2 万条字符串内化进额外只读页。
   通过 `hybrid_snapshot.bin`（注入扩展页）与 `ro_image.bin`
   （分歧区字符串按运行时镜像解码）解决

反汇编器遇到无法恢复的损坏引用时会打印占位符（`<unreadable-object>`、
`<diverged-ro-object>`、`<bad-string>`）并继续；尾部截断时以退出码 77
结束，已输出内容仍然可用。

## 构建反汇编器

以 V8 15.0.245.31（Electron 43）为例，完整步骤见
[Disassembler/BUILD-15.0.245.31.md](./Disassembler/BUILD-15.0.245.31.md)。

旧版本（≤ 11.3）的构建步骤见
[README.old.md](./README.old.md#building-the-disassembler)，要点：

```sh
# 1. checkout 对应 v8 版本
# 2. 打补丁：git apply -3 Disassembler/v8.patch
# 3. 生成构建配置并调整 args.gn
python3 tools/dev/v8gen.py x64.release
# 4. 编译静态库
ninja -C out.gn/x64.release v8_monolith
# 5. 编译 v8dasm（Node 构建加 -DV8_COMPRESS_POINTERS 关闭；Electron 构建加
#    -DV8_COMPRESS_POINTERS -DV8_ENABLE_SANDBOX）
```
