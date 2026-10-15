#!/usr/bin/env python3
"""按 13 位申请编码查询是否中签（只读公开公示数据）。

用法：
  python3 scripts/lookup.py 4748111419156            # 默认查最新一期家庭和个人
  python3 scripts/lookup.py 4748111419156 --period 2025-P2 --kind person
  python3 scripts/lookup.py --list                   # 列出可查期次
"""
from __future__ import annotations

import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARSED = os.path.join(ROOT, "data", "parsed")


def rows() -> list[dict]:
    out = []
    for f in sorted(os.listdir(PARSED)):
        if f.endswith(".json"):
            out.append(json.load(open(os.path.join(PARSED, f), encoding="utf-8")))
    return sorted(out, key=lambda r: (r["period"], r["kind"]), reverse=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("code", nargs="?", help="13 位申请编码")
    ap.add_argument("--period", help="如 2026-P1")
    ap.add_argument("--kind", default="person", choices=["person", "unit"])
    ap.add_argument("--list", action="store_true", help="列出可查期次")
    a = ap.parse_args()
    data = rows()
    if a.list or not a.code:
        print(f"{'期次':<9}{'类别':<8}{'条数':>7}  种子")
        for r in data:
            print(f"{r['period']:<9}{r['kind_slug']:<8}{r['count']:>7}  {r['facts'].get('seed','?')}")
        return
    code = str(a.code).strip()
    if not (code.isdigit() and len(code) == 13):
        raise SystemExit("申请编码应为 13 位数字")
    targets = [r for r in data if (a.period is None or r["period"] == a.period) and r["kind_slug"] == a.kind]
    if not targets:
        raise SystemExit("没有匹配的期次，用 --list 查看")
    for r in targets:
        hit = [t for t in r["triples"] if t[2] == code]
        if hit:
            print(f"[中签] {r['period']} {r['kind_slug']}：序号 {hit[0][0]}，摇号基数序号 {hit[0][1]}，"
                  f"种子数 {r['facts'].get('seed','?')}")
        else:
            print(f"[未中签] {r['period']} {r['kind_slug']}：{r['count']} 条中签记录中无此编码"
                  f"（池大小 {r['facts'].get('pool_size','?')}）")


if __name__ == "__main__":
    main()
