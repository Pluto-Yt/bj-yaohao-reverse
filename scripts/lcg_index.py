#!/usr/bin/env python3
"""精确检验：LCG 是否直接在「池序号空间」递推（模 = 池大小 N 或 N±1、10 的幂等）。

若 i_{k+1} = (a*i_k + c) mod M 成立，则 a 可由相邻差精确解出：
    a ≡ (i_{k+1}-i_k) / (i_k-i_{k-1})  (mod M)
无需搜索；解出后全序列验证。同时试乘同余（c=0）与倒序。
"""
from __future__ import annotations

import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARSED = os.path.join(ROOT, "data", "parsed")


def moduli(n: int) -> list[int]:
    return [n, n + 1, n - 1, 2**31, 2**31 - 1, 2**32, 10**9, 10**6, 10**8, 65536]


def verify(a: int, c: int, m: int, seq: list[int], n: int, skip_dupes: bool = True) -> bool:
    """从 seq[0] 出发按 i' = (a*i+c) mod m 递推，映射回 [1,n] 后与 seq 比较。"""
    x = seq[0]
    seen = {seq[0]} if skip_dupes else set()
    for want in seq[1:]:
        for _ in range(50):
            x = (a * x + c) % m
            i = x % n + 1
            if skip_dupes and i in seen:
                continue
            seen.add(i)
            break
        else:
            return False
        if i != want:
            return False
    return True


def solve_affine(seq: list[int], m: int, offset: int = 0) -> tuple[int, int] | None:
    """用 seq[offset..offset+2] 解 a, c。"""
    i0, i1, i2 = seq[offset], seq[offset + 1], seq[offset + 2]
    d0, d1 = (i1 - i0) % m, (i2 - i1) % m
    try:
        a = d1 * pow(d0, -1, m) % m
    except ValueError:
        return None
    return a, (i1 - a * i0) % m


def solve_multiplicative(seq: list[int], m: int) -> int | None:
    try:
        return seq[1] * pow(seq[0], -1, m) % m
    except ValueError:
        return None


def scan(period: str, kind: str) -> list[dict]:
    row = json.load(open(os.path.join(PARSED, f"{period}_{kind}.json"), encoding="utf-8"))
    f = row["facts"]
    n = int(f.get("pool_size") or f.get("valid_codes"))
    idx = [t[1] for t in row["triples"]]
    hits = []
    for order_name, seq in (("正序", idx), ("倒序", idx[::-1])):
        for m in moduli(n):
            for offset in range(0, 8):
                got = solve_affine(seq, m, offset)
                if not got:
                    continue
                a, c = got
                if verify(a, c, m, seq, n):
                    hits.append({"period": period, "kind": kind, "order": order_name,
                                 "modulus": m, "a": a, "c": c, "model": "仿射 i'=(a*i+c) mod M"})
                    print(f"  ★ {period} {kind} {order_name} M={m} a={a} c={c} —— 全序列复现成功")
            am = solve_multiplicative(seq, m)
            if am is not None and verify(am, 0, m, seq, n):
                hits.append({"period": period, "kind": kind, "order": order_name,
                             "modulus": m, "a": am, "c": 0, "model": "乘同余 i'=a*i mod M"})
                print(f"  ★ {period} {kind} {order_name} M={m} a={am} (c=0) —— 全序列复现成功")
    return hits


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--period", default="2026-P1")
    ap.add_argument("--kind", default="person")
    args = ap.parse_args()
    targets = []
    if args.all:
        for f in sorted(os.listdir(PARSED)):
            if f.endswith(".json"):
                p, k = f[:-5].rsplit("_", 1)
                targets.append((p, k))
    else:
        targets = [(args.period, args.kind)]
    total = 0
    for p, k in targets:
        print(f"== {p} {k}")
        total += len(scan(p, k))
    print(f"命中总数: {total}")
    if total:
        json.dump({"note": "见 stdout"}, open(os.path.join(ROOT, "data", "index_lcg_hits.json"), "w"))


if __name__ == "__main__":
    main()
