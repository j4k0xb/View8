# V8 字节码保护与反编译原理（写给不了解 V8 的人）

> 本文讲清楚三件事：
> 1. JavaScript 源码是怎么被"编译保护"成 `.jsc` 文件的（正向）；
> 2. `.jsc` 又是怎么被一步步还原成可读 JS 的（反向）；
> 3. 为什么老版本 V8（≤11.x）的反编译只要一个工具，而新版（15.x）还需要
>    `ro_image.bin` / `hybrid_snapshot.bin` 两个配套文件。
>
> 文中所有数值（哈希值、字节数、页号等）均来自本仓库开发过程中的**实际测量**
> （见[附录](#七实测数据附录)，可用仓库脚本复现），外部结论附参考链接。

---

## 一、正向：JS 源码如何变成受保护的 jsc

### 1.1 V8 执行 JS 的流水线

V8 拿到 JS 源码后并不是直接解释文本，而是先编译成自家指令集——
**Ignition 字节码**——再由解释器逐条执行；热函数另由 TurboFan/Maglev
生成本机代码（与本文无关，略）。

```
 JS 源码
    │  Parser（解析）
    ▼
  AST（抽象语法树）
    │  Ignition 编译器（字节码生成）
    ▼
 BytecodeArray（字节码数组，驻留在 V8 堆中）
    │  Ignition 解释器
    ▼
  执行 ──── 热点函数 ──► Sparkplug/Maglev/TurboFan ──► 本机代码
```

字节码长什么样？下面是 `view8.py` 反汇编输出的一行真实样例
（`LdaConstant` = 把常量池第 5 项装入累加器）：

```
0x2c7e01012a0c @ 40 : 33 f8 05 0a   GetNamedProperty r1, [5:"message"], FBV[2]
                     └┬┘ └─┬─┘ └┬┘    └───────┬──────┘  └────┬────┘
                   操作码 寄存器 常量索引          │         反馈向量槽位
                                                 └─ 常量池第 5 项是字符串 "message"
```

### 1.2 序列化：把字节码"打包"成文件

V8 提供 code cache API（`v8::ScriptCompiler::kProduceCodeCache`），可以把
编译产物（字节码 + 常量池 + 作用域信息 + 函数元数据）序列化成二进制，
下次加载时用 `kConsumeCodeCache` 直接反序列化，跳过解析编译。
这本是性能优化（见 v8.dev 官方博客 [Code caching for JavaScript developers]），
但社区立刻意识到它天然适合**源码保护**：既然字节码能落盘加载，
就可以不发布 `.js` 只发布编译产物。

代表性工具 **[bytenode]**：把入口 JS 编译成 `.jsc`，运行时用一个小
loader 加载；[electron-vite 官方指南]也推荐"V8 字节码 + ASAR 完整性校验"
作为 Electron 应用的发布保护方案。

```
 开发者侧（正向保护）：
 ┌────────────┐   bytenode / electron-vite    ┌─────────────────────┐
 │ app.js 源码 │ ───────────────────────────► │ app.jsc（字节码缓存） │
 └────────────┘   kProduceCodeCache 序列化     └─────────────────────┘
                                                        │ 只发布这个
                                                        ▼
                                               最终用户拿到 .jsc，拿不到源码
```

### 1.3 jsc 文件头：为什么换版本就加载不了

序列化数据的开头是一个定长校验头（字段定义在 V8 源码
`src/snapshot/code-serializer.cc` / `snapshot.cc`，本仓库开发时逐字段核对过）：

```
偏移   字段                      作用                              实测值（新版样本.jsc）
─────  ───────────────────────  ────────────────────────────────  ─────────────────────────
+0     magic number             0xC0DE0000 ^ 外部引用表大小 kSize   0xC0DE06C6 → kSize=1734
+4     version hash             V8 版本四元组的哈希                0x83276F04（15.0.245.31）
+8     source hash              原始源码文本的哈希                 0x002F02B2
+12    flag hash                V8 运行旗标组合的哈希              0x24360E99
+16    RO snapshot checksum     只读快照校验和（V8 12+ 新增）      0x67D8D026
+20    payload length           载荷长度                           6,873,872
+24    checksum                 载荷校验和                         …
```

加载时 V8 逐项比对，**任何一项不匹配就拒绝加载**。这就是"保护"的另一面：
`.jsc` 被版本哈希锁死在产生它的那个 V8 构建上。PTS 的逆向博客
[How we bypassed bytenode and decompiled Node.js] 正是利用这一点反向操作——
自建 V8 并修改版本哈希，让目标 `.jsc` 以为遇到了"原厂"运行时。

Check Point 研究 [Exploring Compiled V8 JavaScript Usage in Malware] 还记录了
恶意软件滥用同一机制做混淆的案例——反向能力因此也有安全价值。

---

## 二、反向：jsc 如何还原成 JS

整体是三段式流水线（即本仓库 `view8.py` 的实际执行链）：

```
 app.jsc
 ─────────► ① 版本探测 ─────────► ② 反序列化+反汇编 ─────────► ③ 翻译+反编译
            Parser/version_detector.py   Bin/<版本>/v8dasm           Parser/ + Translate/
            （纯 Python 哈希爆破）        （打过补丁的 V8 二进制）      （Python）
                                             │                            │
                                             ▼                            ▼
                                        disasm.tmp                  output.js
                                        （寄存器级反汇编文本）        （接近 JS 的代码）
```

### 2.1 第一步：版本探测（这个 jsc 是哪个 V8 编的？）

头部 +4 的版本哈希是单向的，不能直接反查出版本——但版本号是个小空间
（major.minor.build.patch 四个不大的整数），可以**爆破**：
对每个候选版本算哈希，撞上目标值即命中。本仓库 `Parser/version_detector.py`
实现了两种算法（V8 源码 `src/utils/version.h` 中 `Version::Hash()` 的两个时代）：

| 时代 | 算法 | 折叠方向 | 实测样例 |
|---|---|---|---|
| ≤ V8 13.x | `hash_combine(major,minor,build,patch)` | **从右往左**折（patch 先入） | 10.8.168.25 → `0xA8EB6C86`（旧版样本实测命中） |
| V8 14+ | `base::Hasher.Add()` | **从左往右**折（major 先入） | 15.0.245.31 → `0x83276F04`（新版样本实测命中） |

两个算法结果完全不同——这就是老 VersionDetector.exe 认不出 15.x 文件的原因
（它只会旧算法），也是本仓库用 Python 探测器取代它的原因。

### 2.2 第二步：反序列化 + 打印（v8dasm）

拿同版本 V8 源码，打上 `Disassembler/v8.patch` 编译成 `v8dasm`。补丁做两件事：

1. **拆掉校验**：`SanityCheck` 直接返回成功、反序列化器的 magic CHECK 移除
   ——这样即使旗标哈希/源码哈希对不上（反编译时我们根本没有原始源码，
   源码哈希必然对不上）也能继续；
2. **把对象打印出来**：反序列化完成后调用 V8 自带的调试打印器，把每个函数的
   `SharedFunctionInfo`、`BytecodeArray`（含操作码反汇编）、常量池、异常表
   全部输出成文本（`disasm.tmp`，可用 `--keep-disassembly` 保留）。

### 2.3 第三步：解析、翻译、反编译（Python）

`Parser/sfi_file_parser.py` 按 `Start/End SharedFunctionInfo` 标记把文本切块、
建函数树；`Translate/translate_table.py` 把每条操作码翻译成表达式
（如 `GetNamedProperty r1, [5:"message"]` → `ACCU = r1["message"]`）；
`Parser/shared_function_info.py` 再做控制流重建（if/for/try 还原）。

反编译不是完美还原（变量名、注释必然丢失，偶见 `ACCU`/`Scope[n][m]` 这类
中间表示），但业务逻辑、字符串常量、调用关系都完整可读。

---

## 三、V8 内部机制速成（看懂下文只需这三个概念）

**堆（Heap）**：V8 把所有运行时对象（函数、字符串、数组……）放在一片连续
内存里。指针压缩（x64 默认开启）后，对象地址是 4GB "笼子"内的 32 位偏移。

**只读堆（Read-Only Heap，下称 RO 堆）**：一批永不修改的对象（Map、空数组、
内化字符串……）单独放一片只读内存，多个 isolate 共享。它按 256KB 一页组织，
从地址 0 开始：第 0 页、第 1 页……`.jsc` 里对这些对象的引用就记成
`(页号, 页内偏移)`。V8 9.5 起引入跨 isolate 共享 RO 堆（见 [V8 9.5 release notes]）。

**启动快照（Startup Snapshot）**：V8 构建时用 mksnapshot 把初始化好的堆
序列化成镜像嵌进二进制，运行时直接反序列化，冷启动不用从零构建堆。
Electron/Node 二进制里嵌着完整的快照 blob（本文的 `ro_image.bin` 就是从
App 二进制里切出来的这个 blob 的 RO 段）。

```
 V8 笼子（4GB，指针压缩）
 ┌────────────────────────────────────────────────┐
 │ 只读堆（共享，256KB/页）                          │
 │ ┌────────┐ ┌────────┐        ┌────────┐ ┌─────┐ │      ┌──────────────────┐
 │ │ 页 0-5 │ │ 页 6/7 │  ...   │ 页 8/9 │ │ ... │ │      │ 普通堆（每 isolate）│
 │ │静态对象 │ │builtin │        │Node 字符│      │ │      │ 老生代/新生代/代码 │
 │ │跨构建一致│ │Code 等 │        │串（运行时）│     │ │      │ jsc 反序列化到这里 │
 │ └────────┘ └────────┘        └────────┘ └─────┘ │      └──────────────────┘
 └────────────────────────────────────────────────┘
```

---

## 四、版本演进：反编译难度为什么变了

| | ≤ V8 11.3（Node 16-20 / Electron ≤22 时代） | V8 12+ / 15.x（Node 24 / Electron 43 时代） |
|---|---|---|
| 版本哈希 | 逆序折叠，老探测器认得 | **正序折叠**，老探测器全部失明 |
| RO 堆内容 | 完全由源码+构建参数决定 | **运行时会扩展**：Node 引导把 ~2 万条字符串内化进第 8/9 页 |
| 外部引用表 kSize | 官方构建可复现 | 构建参数敏感（`v8_wasm_random_fuzzers` 一项就 ±1，实测 1734 vs 1735） |
| 页 6/7（builtin Code 区） | 可字节级复现 | **随编译产物（PGO/clang）位移**，同版本号的重编译也不一致 |
| 反编译所需 | 一个 `v8dasm` | `v8dasm` + `hybrid_snapshot.bin` + `ro_image.bin` |

### 4.1 为什么旧版不需要那两个 .bin 文件

≤11.3 时代，`.jsc` 引用的 RO 对象全部落在**静态区**（页 0-5 一带）。
这片区域由 V8 源码里的静态根表（`src/roots/static-roots.h`）钉死地址，
任何"相同源码 + 相同构建参数"的构建产物字节级一致。所以拿同版本 V8 源码
按官方参数编译一个 `v8dasm`，它自己的 RO 堆和产 jsc 的运行时**天然对齐**，
引用 `(页, 偏移)` 直接命中正确对象——本仓库 `Bin/10.8.168.25/v8dasm`
反编译 Electron 22 的 jsc 至今零配置可用，就是这个原理（旧版样本实测）。

### 4.2 新版出了什么问题（按发现顺序，全部实测）

1. **页 8/9 凭空出现**：给官方 Electron 43 生成的 `.jsc` 引用
   `(8, …)`、`(9, …)`，而自建 v8dasm 的 RO 堆只有 8 页（0-7）。
   用 `--trace-deserialization` 让真 Electron 消费同一文件，追踪到第 8/9 页
   内容是 `promise_trace_id`、`node:module_export_names`、`BROTLI_OPERATION_FINISH`
   这类**Node 引导阶段内化的字符串**（约 346KB、2 万余条）。机制：新版 V8
   的可扩展只读快照允许运行时把新内化的字符串分配进 RO 堆，Node 启动时
   塞满了两页。这些字符串不存在于任何 V8 源码构建里，只能从运行时二进制的
   快照 blob 里拿来。
2. **页 6/7 对不齐**：把官方 Electron 的第 8/9 页拼进自建 RO 堆后，
   部分 `.jsc` 引用仍解析到"对象中间"，打印出乱码常量（ASCII 字节被
   当 UTF-16 双字节拼成"汯敶㩲"式伪汉字）。逐字节比对快照镜像发现：
   页 0-5 完全一致、页 6/7 布局有约 10KB 级差异——这片是 builtin Code
   对象区，对象大小取决于编译产物（PGO、clang 版本），**同版本号的不同
   编译构建天然不一致**。
3. **决定性证据**：目标 App（版本串同样是 15.0.245.31-electron.0 的重编译运行时）
   内嵌快照的 RO 段 = 632,040 字节，官方 Electron 43.5.0 = 631,744 字节，
   **差 296 字节**——证实 App 用的是同版本号的自编译运行时。换成 App 自己的
   快照后乱码归零（对照数据见第 5.3 节）。

---

## 五、ro_image.bin 与 hybrid_snapshot.bin 的作用

两个文件都放在 `Bin/<版本>/` 下与 v8dasm 同目录，`view8.py` 自动通过
环境变量注入（`V8DASM_SNAPSHOT_BLOB` / `V8DASM_RO_IMAGE`），分别解决
上面两个问题：

### 5.1 hybrid_snapshot.bin —— 让第 8/9 页真实存在

```
 我们自己的启动 blob                     拼接后的 hybrid_snapshot.bin
 ┌─────────────────────────┐            ┌─────────────────────────┐
 │ header                  │            │ header（重算偏移）        │
 │ RO 镜像: 页0-7（自建）    │  ──拼──►   │ RO 镜像: 页0-7（自建）    │
 │ startup/shared/ctx(自建) │            │         + 页8/9（App的）  │ ← 注入
 └─────────────────────────┘            │ startup/shared/ctx(自建) │
                                        └─────────────────────────┘
```

自建部分保证与 v8dasm 二进制自身完全自洽（builtin 表、根表全部对得上），
注入的第 8/9 页让 `.jsc` 对 Node 字符串页的引用直接命中真实对象。
制作方法：解析双方 RO 镜像的字节码记录（`kAllocatePageAt`/`kSegment`），
把 App 快照里自建 RO 没有的页记录插到终结记录之前（`tools/extract_runtime_blob.py`）。

### 5.2 ro_image.bin —— 分歧区的"预言机"

页 6/7 无法复现（依赖 App 的编译产物），引用落进去必然错。
解决办法：**不从堆里解析，改查字典**——把 App 快照的 RO 段原样存成
`ro_image.bin`，反序列化器遇到指向分歧区（页 6 尾部 + 页 7）的引用时，
先问预言机：这个 `(页, 偏移)` 在 App 镜像里是什么对象？是字符串就按镜像
字节重建一个真字符串，是别的对象就用 `undefined` 占位。

```
 .jsc 里的引用 (7, 0x97a8)
        │
        ▼
 v8dasm 反序列化器：这个地址在分歧区吗？
        │是                              │否
        ▼                                ▼
 查 ro_image.bin 镜像字节          直接读本机 RO 堆
 map=0x155(字符串)? → 按 len/content 重建字符串
 其他 map          → undefined 占位
```

### 5.3 为什么必须用 App 自己的二进制

预言机的正确性完全取决于"镜像布局 == 产 jsc 的运行时布局"。
官方 Electron 和 App 的重编译版本在第 6/7 页差了 296 字节，
用错镜像就会把引用解码到对象中间。换用 App 专属快照后的实测对照：

| 指标 | 官方 Electron 镜像 | App 专属镜像 |
|---|---|---|
| 乱码常量（"汯敶"类） | 多处 | **0** |
| subProcessServer / appHostProcess 占位符 | 若干 | **0** |
| index.jsc.js 行数 | 163,690 | **390,152**（多恢复一倍函数） |
| 中文常量行数 | 418 | 617 |

结论已经固化为工作流：**jsc 从哪个 App 来，预言机就从那个 App 的二进制提取**
（见 README"获取最佳反编译效果"章节）。

---

## 六、完整过程图（正向 + 反向一图流）

```
【正向：保护】
 源码 app.js ─► bytenode(kProduceCodeCache) ─► app.jsc ══发布══►
     (版本哈希/旗标哈希/源码哈希写进头部，锁定运行时)

【反向：还原】
 app.jsc
   │ ① Parser/version_detector.py：爆破版本哈希（新旧两算法）
   │    └─► "15.0.245.31" → 自动选 Bin/15.0.245.31/v8dasm
   │ ② v8dasm（打补丁的同版本 V8）：
   │    ├─ 跳过头部校验（源码哈希必然对不上）
   │    ├─ 加载 hybrid_snapshot.bin（RO 堆获得 App 的第 8/9 字符串页）
   │    ├─ 分歧区引用查 ro_image.bin 预言机
   │    └─ 打印全部函数 ─► disasm.tmp
   │ ③ Python：sfi_file_parser 切块建树 → translate_table 逐码翻译
   │    → shared_function_info 控制流重建 ─► output.js
   ▼
 可读 JS（逻辑/字符串/调用关系完整，变量名丢失）
```

---

## 七、实测数据附录

以下数值全部来自本仓库开发过程，可用仓库工具复现
（`Parser/version_detector.py`、`tools/extract_runtime_blob.py`、
`xxd`、`--trace-deserialization`）：

| 项目 | 值 |
|---|---|
| 旧版样本.jsc（Electron 22 / V8 10.8.168.25）| magic 0xC0DE05A9（kSize=1449），版本哈希 0xA8EB6C86，旧算法命中 |
| 新版样本.jsc（V8 15.0.245.31）| magic 0xC0DE06C6（kSize=1734），版本哈希 0x83276F04，新算法命中 |
| 自建 v8dasm（未关 fuzzers）| kSize=1735（多出的 1 = `WasmGenerateRandomModule` 运行时函数） |
| 自建 RO 堆 | 8 页，blob RO 段 295,672 字节 |
| 官方 Electron 43.5.0 快照 | 10 页，RO 段 631,744 字节（页 8/9 = 346,208 字节 Node 字符串） |
| 目标 App 快照 | 10 页，RO 段 632,040 字节（与官方差 296 字节，页 6/7 布局不同） |
| 页一致性比对 | 页 0-5 逐字节一致；页 6 自 0x20198 起、页 7 全部分歧 |
| 版本哈希算法验证 | 旧算法 hash(10,8,168,25)=0xA8EB6C86；新算法 hash(15,0,245,31)=0x83276F04 |
| 替换 App 镜像效果 | 乱码 3 个文件全部归零；index.jsc.js 从 163,690 行增至 390,152 行 |

---

## 参考资料

- [bytenode — GitHub]：JS → V8 字节码编译保护的代表工具
- [electron-vite: Source Code Protection]：V8 字节码 + ASAR 完整性校验的官方保护指南
- [electron-vite: Easy way to protect your Electron source code (dev.to)]：保护方案实践
- [v8.dev: Code caching for JavaScript developers]：code cache 机制的官方说明
- [PTS（Positive Technologies）: How we bypassed bytenode and decompiled Node.js bytecode in Ghidra]：修改版本哈希、自建 V8 反编译的经典文章（Sergey Fedonin，2021-05）
- [Check Point: Exploring Compiled V8 JavaScript Usage in Malware]：.jsc 被恶意软件用做混淆的研究
- [V8 9.5 release notes]：跨 isolate 共享只读堆的引入
- [suleram/View8]：本仓库上游（反编译流水线设计参考，支持到 V8 11.3）
- [jscd]：纯 Rust 实现的 bytenode .jsc 反编译工具（不依赖修改版 V8，与本仓库思路互补，可交叉验证）
- [Reverse engineering an Electron compiled file (reverseengineering.stackexchange.com)]

[bytenode]: https://github.com/bytenode/bytenode
[electron-vite: Source Code Protection]: https://electron-vite.org/guide/source-code-protection
[electron-vite: Easy way to protect your Electron source code (dev.to)]: https://dev.to/alex300300/electron-vite-easy-way-to-protect-your-electron-source-code
[v8.dev: Code caching for JavaScript developers]: https://v8.dev/blog/code-caching-for-devs
[PTS: How we bypassed bytenode and decompiled Node.js]: https://ptswarm.com/blog/how-we-bypassed-bytenode-and-decompiled-node-js-bytecode-in-ghidra/
[Check Point: Exploring Compiled V8 JavaScript Usage in Malware]: https://research.checkpoint.com/2024/exploring-compiled-v8-javascript-usage-in-malware/
[V8 9.5 release notes]: https://v8.dev/blog/v8-release-95
[suleram/View8]: https://github.com/suleram/View8
[jscd]: https://github.com/ejfkdev/jscd
[Reverse engineering an Electron compiled file (reverseengineering.stackexchange.com)]: https://reverseengineering.stackexchange.com/questions/28205/reverse-engineering-an-electron-compiled-file
