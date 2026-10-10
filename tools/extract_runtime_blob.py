#!/usr/bin/env python3
"""从目标运行时二进制（electron / node）提取快照 blob，生成 v8dasm 的
预言机文件（ro_image.bin + hybrid_snapshot.bin）。

为什么需要目标 App 自己的二进制：同版本号的 Electron 重编译构建
（版本串 / kSize / 版本哈希完全相同）在只读堆第 6/7 页的布局会因编译
产物差异（PGO、clang 版本等）而不同。code cache 里的引用按 App 运行时
自己的布局生成；用官方 Electron 的快照做预言机会把引用解码到对象中间，
产生乱码。用 App 自己的快照则完全对齐。

用法：
    python3 tools/extract_runtime_blob.py <运行时二进制> <输出目录> \
            [--our-blob <我们构建的 mksnapshot 输出>] [--version <版本串>]

    <运行时二进制>  App 内嵌的 electron 可执行文件（Linux 上通常叫
                    electron，Windows 上是 electron.exe；node 二进制也可）
    <输出目录>      生成 ro_image.bin / hybrid_snapshot.bin（与 v8dasm
                    放同一目录即自动生效）
    --our-blob      v8 源码树里 `mksnapshot --startup_blob` 的输出，
                    用于拼 hybrid；缺省则只生成 ro_image.bin
    --version       形如 15.0.245.31-electron.0 的版本串；缺省时自动扫描
"""

import argparse
import os
import re
import struct
import sys


def parse_blob_header(data, start):
    """校验 start 处是否为合法快照 blob 头，返回信息字典或 None。"""
    if start + 96 > len(data):
        return None
    num_ctx, rehash, csum, ro_csum = struct.unpack_from("<IIII", data, start)
    if not (1 <= num_ctx <= 20):
        return None
    ver = data[start + 16:start + 80].split(b"\0")[0].decode("latin-1")
    if not re.match(r"^\d+\.\d+\.\d+(\.\d+)?([-.\w]*)$", ver):
        return None
    startup_off, shared_off = struct.unpack_from("<II", data, start + 80)
    ctx_offs = struct.unpack_from(f"<{num_ctx}I", data, start + 88)
    ro_start = (88 + num_ctx * 4 + 7) & ~7
    offs = [startup_off, shared_off] + list(ctx_offs)
    if any(o <= ro_start for o in offs) or sorted(offs) != offs:
        return None
    if any(o > len(data) - start for o in offs):
        return None
    return {
        "start": start, "version": ver, "num_ctx": num_ctx,
        "ro_start": ro_start, "startup_off": startup_off,
        "ro_size": startup_off - ro_start,
    }


def find_blobs(data, version):
    """扫描二进制中所有快照 blob，按版本过滤，返回候选列表。"""
    hits = []
    needle = version.encode() if version else None
    pos = 0
    while True:
        if needle:
            i = data.find(needle, pos)
        else:
            # 无版本串时按 blob 头特征粗扫：+16 处是 64 字节版本串
            i = data.find(b"\0\0\0\0", pos)  # 太慢，改为启发式跳过
            break
        if i < 0:
            break
        pos = i + 1
        info = parse_blob_header(data, i - 16)
        if info:
            hits.append(info)
    if needle is None:
        # 兜底：常见的 v8 版本串形式扫描（数字开头）
        for m in re.finditer(rb"\d{1,2}\.\d{1,2}\.\d{1,4}(\.\d{1,4})?[-.\w]{0,24}\0",
                             data):
            i = m.start()
            info = parse_blob_header(data, i - 16)
            if info:
                hits.append(info)
    # 去重（同一起点只留一次）
    uniq = {}
    for h in hits:
        uniq[h["start"]] = h
    return list(uniq.values())


def read_u30(d, pos):
    raw = int.from_bytes(d[pos:pos + 4].ljust(4, b"\0"), "little")
    n = (raw & 3) + 1
    raw = int.from_bytes(d[pos:pos + n], "little")
    bits = n * 8 - 2
    return (raw >> 2) if bits >= 32 else ((raw >> 2) & ((1 << bits) - 1)), pos + n


def parse_ro_records(d, ro_start, startup_off):
    """解析 RO 镜像字节码记录，返回 (记录列表, 终结记录)。"""
    pos = ro_start + 8  # 跳过 SerializedData 头（magic + payload 长度）
    records = []
    while pos + 1 < startup_off:
        op = d[pos]
        start = pos
        pos += 1
        page = None
        if op in (0, 1):
            page, pos = read_u30(d, pos)
            _area, pos = read_u30(d, pos)
            if op == 1:
                pos += 4
        elif op == 2:
            page, pos = read_u30(d, pos)
            _off, pos = read_u30(d, pos)
            size, pos = read_u30(d, pos)
            pos += size
        elif op == 4:
            pass
        elif op == 5:
            _v, pos = read_u30(d, pos)
            records.append((5, None, d[start:pos]))
            return records, d[start:pos]
        else:
            raise ValueError(f"RO 镜像解析失败：未知字节码 {op} @ {start}")
        records.append((op, page, d[start:pos]))
    raise ValueError("RO 镜像解析失败：缺少终结记录")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("binary", help="目标运行时二进制（electron / node）")
    ap.add_argument("outdir", help="输出目录（通常为 Bin/<版本>/）")
    ap.add_argument("--our-blob", default=None,
                    help="我们构建的 mksnapshot --startup_blob 输出，用于拼接 hybrid")
    ap.add_argument("--version", default=None,
                    help="版本串，如 15.0.245.31-electron.0；缺省自动扫描")
    args = ap.parse_args()

    data = open(args.binary, "rb").read()
    print(f"读取二进制：{args.binary}（{len(data)} 字节）")

    blobs = find_blobs(data, args.version)
    if not blobs:
        print("错误：未找到快照 blob。请确认输入是完整的 electron/node 可执行文件，"
              "或用 --version 指定版本串。")
        return 1
    for b in blobs:
        print(f"  候选 blob @0x{b['start']:x}: version={b['version']} "
              f"num_ctx={b['num_ctx']} ro_size={b['ro_size']}")
    # 取 RO 段最大的（Node 的快照，而非 Blink 的）
    best = max(blobs, key=lambda b: b["ro_size"])
    print(f"选用 blob @0x{best['start']:x}（version={best['version']}，"
          f"RO {best['ro_size']} 字节）")

    os.makedirs(args.outdir, exist_ok=True)

    # 1) ro_image.bin：RO 段 + 少量余量（预言机只读 RO 段）
    ro_path = os.path.join(args.outdir, "ro_image.bin")
    with open(ro_path, "wb") as f:
        f.write(data[best["start"]:best["start"] + best["startup_off"] + 64])
    print(f"已生成 {ro_path}")

    # 2) hybrid_snapshot.bin：我们的 blob + 运行时多出的 RO 页记录
    if args.our_blob:
        ours = open(args.our_blob, "rb").read()
        o_num_ctx = struct.unpack_from("<I", ours, 0)[0]
        o_startup, o_shared = struct.unpack_from("<II", ours, 80)
        o_ro0 = (88 + o_num_ctx * 4 + 7) & ~7
        our_ro = ours[o_ro0:o_startup]
        our_startup = ours[o_startup:o_shared]
        our_shared = ours[o_shared:struct.unpack_from("<I", ours, 88)[0]]
        our_ctx = ours[struct.unpack_from("<I", ours, 88)[0]:]

        o_recs, _ = parse_ro_records(ours, o_ro0, o_startup)
        n_recs, _ = parse_ro_records(data, best["start"] + best["ro_start"],
                                     best["start"] + best["startup_off"])
        our_pages = {p for _, p, _ in o_recs if p is not None}
        extra = [r for _, p, r in n_recs if p is not None and p not in our_pages]
        finalize = [r for op, p, r in o_recs if op == 5]
        body = [r for op, p, r in o_recs if op != 5]
        print(f"  我们的 RO 页：{sorted(our_pages)}；注入运行时页："
              f"{sorted({p for _, p, _ in n_recs if p is not None and p not in our_pages})}")

        new_ro = bytearray(our_ro[:8])
        for r in body + extra + finalize:
            new_ro += r
        struct.pack_into("<I", new_ro, 4, len(new_ro) - 8)

        header = ours[:o_ro0]
        ro_off = o_ro0
        startup_off = ro_off + len(new_ro)
        shared_off = startup_off + len(our_startup)
        ctx0_off = shared_off + len(our_shared)
        out = bytearray(ctx0_off + len(our_ctx))
        out[:len(header)] = header
        struct.pack_into("<II", out, 80, startup_off, shared_off)
        struct.pack_into("<I", out, 88, ctx0_off)
        out[ro_off:ro_off + len(new_ro)] = new_ro
        out[startup_off:startup_off + len(our_startup)] = our_startup
        out[shared_off:shared_off + len(our_shared)] = our_shared
        out[ctx0_off:] = our_ctx
        hyb_path = os.path.join(args.outdir, "hybrid_snapshot.bin")
        with open(hyb_path, "wb") as f:
            f.write(out)
        print(f"已生成 {hyb_path}")

    print("完成。将两个 .bin 文件与 v8dasm 放在同一目录即可自动生效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
