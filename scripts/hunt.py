#!/usr/bin/env python3
"""方案B：从公开公示数据反解摇号用的线性同余发生器（LCG）参数。

模型假设
--------
  摇号池有 N 个「摇号基数序号」(1..N)；配置程序用伪随机数发生器取 9600(或 400) 个序号：
      x_{k+1} = (a * x_k + c) mod m          # 待求 a, c, m
      u_k     = x_k / m                      # 归一到 [0,1)
      i_k     = floor(u_k * N) + 1           # 映射A：缩放取整
    或
      i_k     = x_k mod N + 1                # 映射B：取模
  公示按「序号」列给出 i_k，猜测即抽取顺序。

方法
----
  1. 反解：映射A 下 x_k ∈ [ceil((i-1)m/N), ceil(i*m/N)-1]（宽度 ≈ m/N）；
     映射B 下 x_k ∈ {i-1, i-1+N, i-1+2N, ...}。
  2. 对连续三连 (x_k, x_{k+1}, x_{k+2})，真参数满足  a*d_k ≡ d_{k+1} (mod m)，
     d = 相邻差。对每个位置枚举出候选 a 并投票；真 a 会在「d_k 与 m 互素」的位置
     反复出现，随机值只出现一次。
  3. 得票高的 a 再枚举 c 候选，用前若干位与全序列验证（含「重复则跳过重抽」语义）。

不预设 m：对 2^31、2^31-1、2^32、2^48、10^9 等常见模数逐一试，并试正序/倒序。
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from math import ceil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARSED = os.path.join(ROOT, "data", "parsed")

MODULI = [2**31, 2**31 - 1, 2**32, 2**48, 10**9, 10**10]


def load(period: str, kind: str) -> dict:
    p = os.path.join(PARSED, f"{period}_{kind}.json")
    if not os.path.exists(p):
        sys.exit(f"缺少解析产物：{p}（先跑 pipeline.py parse）")
    return json.load(open(p, encoding="utf-8"))


def interval_scale(i: int, n: int, m: int) -> list[int]:
    """映射A：x 满足 floor(x/m*n)+1 == i（整数 ceiling，避免浮点丢精度）。"""
    lo = ((i - 1) * m + n - 1) // n
    hi = (i * m + n - 1) // n - 1
    return list(range(lo, hi + 1))


def interval_mod(i: int, n: int, m: int) -> list[int]:
    """映射B：x 满足 x % n + 1 == i。"""
    return list(range(i - 1, m, n))


def vote_a(indices: list[int], n: int, m: int, mapping: str, positions: int) -> collections.Counter:
    """对每个位置枚举候选 a 并投票。"""
    iv = interval_scale if mapping == "scale" else interval_mod
    xs = [iv(i, n, m) for i in indices[: positions + 2]]
    votes: collections.Counter = collections.Counter()
    for k in range(positions):
        seen_a = set()
        for x0 in xs[k]:
            for x1 in xs[k + 1]:
                d0 = (x1 - x0) % m
                if d0 == 0 or d0 % 2 == 0 and m % 2 == 0:
                    continue
                try:
                    inv = pow(d0, -1, m)
                except ValueError:
                    continue
                for x2 in xs[k + 2]:
                    d1 = (x2 - x1) % m
                    a = d1 * inv % m
                    if a not in seen_a:
                        seen_a.add(a)
        votes.update(seen_a)
    return votes


def verify(a: int, c: int, x0: int, m: int, n: int, observed: list[int], mapping: str, skip_dupes: bool) -> bool:
    """从 x0 起生成序列，按映射比对（可选「重复则跳过」）。"""
    x = x0
    seen: set[int] = set()
    out: list[int] = []
    limit = len(observed) * 3 + 1000
    for _ in range(limit):
        x = (a * x + c) % m
        i = (x * n // m) + 1 if mapping == "scale" else (x % n) + 1
        if not (1 <= i <= n):
            return False
        if skip_dupes and i in seen:
            continue
        seen.add(i)
        out.append(i)
        if len(out) == len(observed):
            break
    return out == observed


def hunt(period: str, kind: str, positions: int = 12, verbose: bool = True, width_cap: int = 120) -> list[dict]:
    row = load(period, kind)
    facts = row["facts"]
    n = int(facts["pool_size"])
    observed = [t[1] for t in row["triples"]]
    hits: list[dict] = []
    for m in MODULI:
        for mapping in ("scale", "mod"):
            width = m // n + 1 if mapping == "scale" else m // n
            if width > width_cap:
                if verbose:
                    print(f"  m={m:<12d} 映射={mapping:5s} 候选区间宽 {width} > {width_cap}，本方法不适用，跳过")
                continue
            for order_name, seq in (("正序", observed), ("倒序", observed[::-1])):
                votes = vote_a(seq, n, m, mapping, positions)
                top = votes.most_common(5)
                if verbose:
                    print(f"  m={m:<12d} 映射={mapping:5s} {order_name} 候选a宽度≈{width:<6d} "
                          f"最高票={top[0][1] if top else 0}")
                for a, cnt in top:
                    if cnt < 3:
                        continue
                    # 用位置0枚举 c 与起点，先短验后全验
                    iv = interval_scale if mapping == "scale" else interval_mod
                    xs0 = iv(seq[0], n, m)
                    xs1 = iv(seq[1], n, m)
                    for x0 in xs0:
                        for x1 in xs1:
                            c = (x1 - a * x0) % m
                            if verify(a, c, x0, m, n, seq[:8], mapping, True):
                                if verify(a, c, x0, m, n, seq, mapping, True):
                                    hits.append({"period": period, "kind": kind, "m": m,
                                                 "mapping": mapping, "order": order_name,
                                                 "a": a, "c": c, "x0": x0, "votes": cnt})
                                    print(f"  ★ 复现成功: m={m} 映射={mapping} {order_name} a={a} c={c} x0={x0}")
    return hits


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="2026-P1")
    ap.add_argument("--kind", default="person", choices=["person", "unit"])
    ap.add_argument("--positions", type=int, default=12)
    a = ap.parse_args()
    print(f"== 反解 {a.period} {a.kind}")
    hits = hunt(a.period, a.kind, a.positions)
    if not hits:
        print("  未命中任何 (m, 映射, a, c) 组合 —— 见结论：非简单 LCG 或映射假设不符")
    else:
        out = os.path.join(ROOT, "data", "solution.json")
        json.dump(hits, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"  写出 {out}")


if __name__ == "__main__":
    main()
