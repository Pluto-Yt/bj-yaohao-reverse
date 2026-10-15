#!/usr/bin/env python3
"""假设检验：摇号结果的生成方式。

H1 系统抽样：中签序号是「随机起点 + 固定步长」的等差数列
H2 等差数列（模 N）
H3 标准伪随机数发生器参数库（LCG 各家常量 / Java / MT19937）× 种子初始化变体 × 映射
H4 行序（序号列）与 基数序号 / 申请编码 的相关性结构
H5 排序随机键模型（对每个池元素取随机键，取最小的 quota 个）——需 numpy

用法：python3 scripts/hypotheses.py --period 2026-P1 --kind person
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARSED = os.path.join(ROOT, "data", "parsed")

LCG_LIB: dict[str, tuple[int, int, int]] = {
    "MINSTD(16807,0,2^31-1)": (16807, 0, 2**31 - 1),
    "Lehmer(48271,0,2^31-1)": (48271, 0, 2**31 - 1),
    "Lehmer(69621,0,2^31-1)": (69621, 0, 2**31 - 1),
    "ANSI-C(1103515245,12345,2^31)": (1103515245, 12345, 2**31),
    "glibc(1103515245,12345,2^32)": (1103515245, 12345, 2**32),
    "MSVC(214013,2531011,2^31)": (214013, 2531011, 2**31),
    "Borland(22695477,1,2^32)": (22695477, 1, 2**32),
    "NR(1664525,1013904223,2^32)": (1664525, 1013904223, 2**32),
    "Java(25214903917,11,2^48)": (25214903917, 11, 2**48),
    "MMIX(6364136223846793005,1442695040888963407,2^64)":
        (6364136223846793005, 1442695040888963407, 2**64),
    "ParkMiller-C(69069,1,2^32)": (69069, 1, 2**32),
    "GB-example(106,1283,6075)": (106, 1283, 6075),
    "GB-example(5^5^,0,2^31)": (3125, 0, 2**31),
    "Knuth(6364136223846793005,1,2^64)": (6364136223846793005, 1, 2**64),
    "Zx81(75,74,65537)": (75, 74, 65537),
}


def load(period: str, kind: str) -> tuple[dict, list[int], list[int]]:
    row = json.load(open(os.path.join(PARSED, f"{period}_{kind}.json"), encoding="utf-8"))
    facts = row["facts"]
    n = int(facts.get("pool_size") or facts.get("valid_codes"))
    idx = [t[1] for t in row["triples"]]
    code = [int(t[2]) for t in row["triples"]]
    return {"row": row, "n": n, "facts": facts, "quota": row["count"]}, idx, code


def h1_systematic(idx: list[int], n: int, quota: int) -> dict:
    s = sorted(idx)
    step = n / quota
    d = [b - a for a, b in zip(s, s[1:])]
    return {"step_ideal": round(step, 2), "diff_mean": round(statistics.fmean(d), 2),
            "diff_median": statistics.median(d), "diff_min": min(d), "diff_max": max(d),
            "diff_stdev": round(statistics.pstdev(d), 2),
            "equal_spacing": len(set(d)) == 1}


def h2_ap(idx: list[int], n: int, quota: int) -> dict:
    """是否存在 r,step 使集合恰为 {(r+k*step) mod n}。"""
    s = sorted(idx)
    step = round(n / quota)
    for cand in {step, n // quota, math.ceil(n / quota)}:
        if cand <= 0:
            continue
        r = s[0]
        if {((r + k * cand - 1) % n) + 1 for k in range(quota)} == set(idx):
            return {"found": True, "start": r, "step": cand}
    return {"found": False}


def h3_library(n: int, quota: int, seed: int, idx: list[int]) -> list[dict]:
    obs_set, obs_prefix = set(idx), idx[:20]
    hits = []
    for name, (a, c, m) in LCG_LIB.items():
        for init_name in ("x0=seed", "x0=seed*2+1", "丢弃首个输出", "x0=seed^const"):
            for mapping in ("scale", "mod"):
                x = {"x0=seed": seed, "x0=seed*2+1": seed * 2 + 1,
                     "丢弃首个输出": seed, "x0=seed^const": seed ^ 0x5DEECE66D}[init_name] % m
                out, seen = [], set()
                if init_name == "丢弃首个输出":
                    x = (a * x + c) % m
                attempts = 0
                max_attempts = quota * 30
                while len(out) < quota and attempts < max_attempts:
                    attempts += 1
                    x = (a * x + c) % m
                    i = (x * n // m) + 1 if mapping == "scale" else (x % n) + 1
                    if i in seen:
                        continue
                    seen.add(i)
                    out.append(i)
                if len(out) < quota:  # 值域不足以产生 quota 个不同序号，跳过
                    continue
                ov = len(seen & obs_set)
                prefix = sum(1 for u, v in zip(out[:20], obs_prefix) if u == v)
                if ov > 20 or prefix > 2:
                    hits.append({"algo": name, "init": init_name, "mapping": mapping,
                                 "set_overlap": ov, "prefix_match": prefix})
    # MT19937（Python random）几种用法
    for name, fn in {
        "MT19937.randint(1,N)": lambda r: r.randint(1, n),
        "MT19937.floor(random()*N)+1": lambda r: int(r.random() * n) + 1,
    }.items():
        r = random.Random(seed)
        out, seen = [], set()
        while len(out) < quota:
            i = fn(r)
            if i in seen:
                continue
            seen.add(i)
            out.append(i)
        ov = len(seen & obs_set)
        prefix = sum(1 for u, v in zip(out[:20], obs_prefix) if u == v)
        if ov > 20 or prefix > 2:
            hits.append({"algo": name, "init": "seed", "mapping": "-",
                         "set_overlap": ov, "prefix_match": prefix})
    return hits


def h5_sort_keys(n: int, quota: int, seed: int, idx: list[int]) -> dict | None:
    try:
        import numpy as np
    except ImportError:
        return None
    r = np.random.default_rng(seed)
    keys = r.random(n)
    win = set(np.argsort(keys, kind="stable")[:quota] + 1)
    return {"model": "numpy.default_rng(seed) 排序取键", "overlap": len(win & set(idx)),
            "chance": round(quota * quota / n, 1)}


def spearman(xs: list[int], ys: list[int]) -> float:
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        for pos, i in enumerate(order):
            r[i] = pos + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="2026-P1")
    ap.add_argument("--kind", default="person")
    ap.add_argument("--skip-h5", action="store_true", help="跳过排序键模型（需 51M 级数组，慢）")
    a = ap.parse_args()
    meta, idx, code = load(a.period, a.kind)
    n, quota, seed = meta["n"], meta["quota"], int(meta["facts"]["seed"])
    print(f"== {a.period} {a.kind}: 池={n} 取={quota} 种子={seed}")
    print("H1 系统抽样:", h1_systematic(idx, n, quota))
    print("H2 等差数列:", h2_ap(idx, n, quota))
    print("H4 行序相关性: 行序↔基数序号 ρ=%.4f  行序↔申请编码 ρ=%.4f  基数序号↔申请编码 ρ=%.4f"
          % (spearman(list(range(quota)), idx), spearman(list(range(quota)), code), spearman(idx, code)))
    hits = h3_library(n, quota, seed, idx)
    print(f"H3 标准发生器官扫描: 命中 {len(hits)} 个" if hits else
          f"H3 标准发生器官扫描: 无命中（{len(LCG_LIB)} 组 LCG × 4 初始化 × 2 映射 + MT19937 两种用法）")
    for h in hits:
        print("   ★", h)
    h5 = None if a.skip_h5 else h5_sort_keys(n, quota, seed, idx)
    if h5:
        print(f"H5 {h5['model']}: 与公示集合重合 {h5['overlap']}（随机基线 {h5['chance']}）")


if __name__ == "__main__":
    main()
