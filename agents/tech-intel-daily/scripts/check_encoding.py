#!/usr/bin/env python3
r"""编码守卫：在写入飞书 / 落盘之前检查 Mojibake。

真实事故：gen_report.py 里用 \xNN 表示中文。Python 3 中 \xNN 是 Unicode 码点
U+00NN 而非字节，导致双重编码 —— `科` 的正确 UTF-8 是 E7 A7 91，
错误写法产生了 C3 A7 C2 A7 C2 91，飞书里显示成一堆乱码。
而飞书文档标题一旦以错误编码写入就**永久损坏**，只能新建文档。

所以：写之前先扫一遍，比事后修便宜得多。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MOJIBAKE = ["Ã", "Â", "â€", "ï¿½", "\ufffd"]
ESCAPE_HEX = re.compile(r"\\x[0-9a-fA-F]{2}")


def scan_text(text: str, source: str) -> list:
    problems = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for token in MOJIBAKE:
            if token in line:
                problems.append(f"{source}:{line_no} 疑似 Mojibake（发现 {token!r}）")
                break
        if ESCAPE_HEX.search(line):
            problems.append(f"{source}:{line_no} 含 \\xNN 转义，Python 3 中会产生双重编码")
    return problems


def scan_file(path: Path) -> list:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        bom_note = [f"{path.name}: 含 UTF-8 BOM，读取时需用 utf-8-sig"]
    else:
        bom_note = []
    return bom_note + scan_text(raw.decode("utf-8", errors="replace"), str(path.name))


def main():
    # 跳过自身：本文件为了说明问题，正文里必须出现 Mojibake 样本与 \xNN 写法
    targets = [p for p in ROOT.rglob("*.py")
               if "data" not in p.parts and p.name != "check_encoding.py"]
    targets += [p for p in ROOT.rglob("*.md") if "data" not in p.parts]
    problems = []
    for p in targets:
        problems.extend(scan_file(p))
    if problems:
        print(f"[FATAL] 发现 {len(problems)} 处编码风险：")
        for x in problems[:20]:
            print("  " + x)
        sys.exit(1)
    print(f"[ok] 编码守卫通过：扫描 {len(targets)} 个文件，无 Mojibake / \\xNN 转义 / BOM 问题")


if __name__ == "__main__":
    main()
