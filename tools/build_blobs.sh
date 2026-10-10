#!/usr/bin/env bash
# 生成/更新某个版本目录下的预言机文件（ro_image.bin + hybrid_snapshot.bin）。
#
# 为什么需要"App 自己的二进制"：同版本号的 Electron 重编译构建（版本串、
# kSize、版本哈希完全相同）在只读堆第 6/7 页的布局会因编译产物差异
# （PGO、clang 版本等）而不同。jsc 里的引用按 App 运行时自己的布局生成，
# 用官方 Electron 的快照做预言机会把部分引用解码到对象中间，产生乱码。
# 详见 docs/v8-bytecode-principles-zh.md 第五节。
#
# 用法：
#   tools/build_blobs.sh <v8构建输出目录> <App运行时二进制> <Bin/版本目录> [版本串]
#
#   <v8构建输出目录>   自建 v8 的 out.gn/x64.release（内含 mksnapshot）
#   <App运行时二进制>  App 自带的 electron / 主程序 exe（不是官方下载版！）
#   <Bin/版本目录>     通常为 Bin/<v8版本>/
#   [版本串]           形如 15.0.245.31-electron.0；缺省自动扫描
#
# 实测示例（Electron 43.5.0 应用）：
#   tools/build_blobs.sh /root/dev/v8/v8/out.gn/x64.release \
#       /path/to/目标App主程序.exe Bin/15.0.245.31 \
#       15.0.245.31-electron.0
set -euo pipefail

V8_OUT="${1:?用法: build_blobs.sh <v8构建输出目录> <App运行时二进制> <Bin/版本目录> [版本串]}"
APP_BIN="${2:?缺少 App 运行时二进制路径}"
BIN_DIR="${3:?缺少输出目录（如 Bin/15.0.245.31）}"
VERSION="${4:-}"

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MKSNAPSHOT="${V8_OUT}/mksnapshot"
EXTRACT="${REPO_DIR}/tools/extract_runtime_blob.py"
OUR_BLOB="$(mktemp /tmp/our_snapshot.XXXXXX.bin)"
trap 'rm -f "${OUR_BLOB}"' EXIT

[ -x "${MKSNAPSHOT}" ] || { echo "错误: 找不到 ${MKSNAPSHOT}（请先按 Disassembler/BUILD-15.0.245.31.md 构建 v8）"; exit 1; }
[ -f "${APP_BIN}" ]    || { echo "错误: 找不到 ${APP_BIN}"; exit 1; }
[ -f "${EXTRACT}" ]    || { echo "错误: 找不到 ${EXTRACT}"; exit 1; }

# 第 1 步：用自建 v8 的 mksnapshot 生成我们自己的启动快照 blob
# （hybrid 的"自洽底座"，必须与 v8dasm 二进制同一构建）
echo "==> [1/3] 生成基础快照（mksnapshot --startup_blob）"
"${MKSNAPSHOT}" --startup_blob "${OUR_BLOB}"
echo "    基础 blob: $(stat -c%s "${OUR_BLOB}") 字节"

# 第 2 步：从 App 二进制提取运行时快照，生成 ro_image.bin + hybrid_snapshot.bin
echo "==> [2/3] 提取 App 运行时快照并拼接"
if [ -n "${VERSION}" ]; then
    python3 "${EXTRACT}" "${APP_BIN}" "${BIN_DIR}" --our-blob "${OUR_BLOB}" --version "${VERSION}"
else
    python3 "${EXTRACT}" "${APP_BIN}" "${BIN_DIR}" --our-blob "${OUR_BLOB}"
fi

# 第 3 步：校验产物
echo "==> [3/3] 产物校验"
for f in ro_image.bin hybrid_snapshot.bin; do
    p="${BIN_DIR}/${f}"
    if [ -s "${p}" ]; then
        echo "    ${p}: $(stat -c%s "${p}") 字节"
    else
        echo "    警告: ${p} 未生成或为空"; exit 1
    fi
done

echo "完成。直接重新运行 view8.py 即可（同目录自动注入，无需设置环境变量）："
echo "    python3 view8.py <目标.jsc> <输出.js>"
