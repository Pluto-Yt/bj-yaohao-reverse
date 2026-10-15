#!/usr/bin/env python3
"""生成模型判别：在「小池」数据（单位摇号，池 ≈ 5~10 万）上穷举候选实现。

模型（都以 seed 初始化、按 LCG/MT 产生 u 流）：
  M1 直接抽取   : i_k = floor(u_k*N)+1，去重后取 quota 个（顺序即公示行序）
  M2 排序键     : 给池中每项按 u 流赋键，取键最小的 quota 个（集合，行序无关）
  M3 部分洗牌   : Fisher-Yates 前 quota 步，前 quota 个槽位的集合
  M4 逐项重播种 : 第 j 项的键 = 以 (seed+j) 为初值的首个输出

判据：与公示集合的重合数（随机基线 ≈ quota²/N，单位摇号约 2~4 个）。
"""
from __future__ import annotations

import argparse
import json
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARSED = os.path.join(ROOT, "data", "parsed")

LCG_LIB = {
    "MINSTD(16807,0,2^31-1)": (16807, 0, 2**31 - 1),
    "ANSI-C(1103515245,12345,2^31)": (1103515245, 12345, 2**31),
    "glibc(1103515245,12345,2^32)": (1103515245, 12345, 2**32),
    "MSVC(214013,2531011,2^31)": (214013, 2531011, 2**31),
    "NR(1664525,1013904223,2^32)": (1664525, 1013904223, 2**32),
    "Borland(22695477,1,2^32)": (22695477, 1, 2**32),
    "Java(25214903917,11,2^48)": (25214903917, 11, 2**48),
    "MMIX(6364136223846793005,1442695040888963407,2^64)":
        (6364136223846793005, 1442695040888963407, 2**64),
    "Lehmer(48271,0,2^31-1)": (48271, 0, 2**31 - 1),
    "C++minstd(16807,0,2^31-1)": (16807, 0, 2**31 - 1),
}


def load(period: str, kind: str) -> tuple[int, int, int, list[int]]:
    row = json.load(open(os.path.join(PARSED, f"{period}_{kind}.json"), encoding="utf-8"))
    f = row["facts"]
    n = int(f.get("pool_size") or f.get("valid_codes"))
    return n, row["count"], int(f["seed"]), [t[1] for t in row["triples"]]


def stream_lcg(a: int, c: int, m: int, seed: int, count: int, discard_first: bool = False):
    x = seed % m
    if discard_first:
        x = (a * x + c) % m
    for _ in range(count):
        x = (a * x + c) % m
        yield x / m


def stream_mt(seed: int, count: int):
    r = random.Random(seed)
    for _ in range(count):
        yield r.random()


def m1_draw(u, n: int, quota: int) -> list[int]:
    out, seen = [], set()
    for v in u:
        i = int(v * n) + 1
        if i in seen:
            continue
        seen.add(i)
        out.append(i)
        if len(out) == quota:
            break
    return out


def m2_sortkeys(u, n: int, quota: int) -> set[int]:
    keys = []
    for j, v in enumerate(u, start=1):
        keys.append((v, j))
        if len(keys) > quota * 4:
            keys.sort()
            del keys[quota:]
    keys.sort()
    return {j for _, j in keys[:quota]}


def m3_shuffle(u, n: int, quota: int) -> set[int]:
    pool = list(range(1, n + 1))
    it = iter(u)
    for k in range(quota):
        j = k + int(next(it) * (n - k))
        if j >= n:
            j = n - 1
        pool[k], pool[j] = pool[j], pool[k]
    return set(pool[:quota])


def m4_reseed_lcg(a: int, c: int, m: int, seed: int, n: int, quota: int) -> set[int]:
    """第 j 项的键 = 以 seed+j 为首个输出；取键最小的 quota 个。"""
    keys = []
    for j in range(1, n + 1):
        x = (a * (seed + j) + c) % m
        keys.append((x / m, j))
        if len(keys) > quota * 4:
            keys.sort()
            del keys[quota:]
    keys.sort()
    return {j for _, j in keys[:quota]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="2026-P1")
    ap.add_argument("--kind", default="unit")
    ap.add_argument("--top", type=int, default=8)
    args = ap.parse_args()
    n, quota, seed, idx = load(args.period, args.kind)
    obs = set(idx)
    chance = quota * quota / n
    print(f"== {args.period} {args.kind}: 池={n} 取={quota} 种子={seed} 随机基线≈{chance:.2f}")
    results = []
    streams: dict[str, callable] = {}
    for name, (a, c, m) in LCG_LIB.items():
        for dname, disc in (("", False), ("+丢弃首输出", True)):
            streams[f"LCG {name}{dname}"] = (
                lambda cnt, a=a, c=c, m=m, d=disc, s=seed: stream_lcg(a, c, m, s, cnt, d))
    streams["MT19937"] = lambda cnt: stream_mt(seed, cnt)
    for sname, factory in streams.items():
        # M1 需要 quota 次生成；M2/M3 需要 n 次
        u_short = list(factory(quota * 4))
        for mname, fn in (("M1 抽取", lambda u: set(m1_draw(u, n, quota))),
                          ("M2 排序键", lambda u: m2_sortkeys(u, n, quota)),
                          ("M3 部分洗牌", lambda u: m3_shuffle(u, n, quota))):
            got = fn(u_short if mname == "M1 抽取" else factory(n))
            results.append((len(got & obs), sname, mname))
    for name, (a, c, m) in LCG_LIB.items():
        got = m4_reseed_lcg(a, c, m, seed, n, quota)
        results.append((len(got & obs), f"LCG {name}", "M4 逐项重播种"))
    results.sort(reverse=True)
    print(f"共试 {len(results)} 个组合，最高的 {args.top} 个：")
    for ov, s, mdl in results[: args.top]:
        flag = "  ★★ 命中" if ov > max(10, chance * 5) else ""
        print(f"  重合 {ov:5d}  {s:52s} {mdl}{flag}")


if __name__ == "__main__":
    main()
