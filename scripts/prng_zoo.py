#!/usr/bin/env python3
"""PRNG 动物园：把「软件实现里真实出现过」的一大批发生器 + 取值方式，一次性对着公示数据判。

覆盖：
  Java  java.util.Random（48 位 LCG, nextInt/nextDouble）
  C#    .NET Framework Random（Knuth 减法发生器, Sample）
  C++   std::mt19937(seed) 的 init_genrand（与 Python 的 init_by_array 不同）+ 取模/缩放
  标准  MINSTD / ANSI-C / MSVC / NR / Java / MMIX 的 nextDouble 等价用法
  numpy RandomState(seed) 与 default_rng(seed)
  哈希  SHA-256 / SHA-1 / MD5 对 (seed, k) 派生 → 取模 / 缩放；以及「哈希键排序取前 quota」

判据：与公示集合的重合数（随机基线 ≈ quota²/N），以及行序是否逐个吻合。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARSED = os.path.join(ROOT, "data", "parsed")


# ---------- 各大平台的 PRNG ----------
class JavaRandom:
    def __init__(self, seed: int):
        self.s = (seed ^ 0x5DEECE66D) & ((1 << 48) - 1)

    def next(self, bits: int) -> int:
        self.s = (self.s * 0x5DEECE66D + 0xB) & ((1 << 48) - 1)
        return self.s >> (48 - bits)

    def next_int(self, bound: int) -> int:
        if bound & (bound - 1) == 0:
            return (bound * self.next(31)) >> 31
        while True:
            bits = self.next(31)
            val = bits % bound
            if bits - val + (bound - 1) >= 0:
                return val

    def next_double(self) -> float:
        return ((self.next(26) << 27) + self.next(27)) / float(1 << 53)


class CSharpRandom:
    """System.Random(.NET Framework) 的 Knuth 减法发生器。"""

    def __init__(self, seed: int):
        MBIG, MSEED = 2147483647, 161803398
        seed = abs(seed) % MBIG
        sa = [0] * 56
        mj = MSEED - seed
        sa[55] = mj
        mk = 1
        for i in range(1, 55):
            ii = (21 * i) % 55
            sa[ii] = mk
            mk = mj - mk
            if mk < 0:
                mk += MBIG
            mj = sa[ii]
        for _ in range(4):
            for i in range(1, 56):
                sa[i] -= sa[1 + (i + 30) % 55]
                if sa[i] < 0:
                    sa[i] += MBIG
        self.sa, self.inext, self.inextp = sa, 0, 21

    def sample(self) -> float:
        self.inext += 1
        if self.inext >= 56:
            self.inext = 1
        self.inextp += 1
        if self.inextp >= 56:
            self.inextp = 1
        r = self.sa[self.inext] - self.sa[self.inextp]
        if r == 2147483647:
            r -= 1
        if r < 0:
            r += 2147483647
        self.sa[self.inext] = r
        return r * (1.0 / 2147483647)


class MT19937InitGenrand:
    """C/C++ std::mt19937 单参数构造（init_genrand）。"""

    def __init__(self, seed: int):
        self.mt = [0] * 624
        self.mt[0] = seed & 0xFFFFFFFF
        for i in range(1, 624):
            self.mt[i] = (1812433253 * (self.mt[i - 1] ^ (self.mt[i - 1] >> 30)) + i) & 0xFFFFFFFF
        self.idx = 624

    def _gen(self) -> None:
        for i in range(624):
            y = (self.mt[i] & 0x80000000) + (self.mt[(i + 1) % 624] & 0x7FFFFFFF)
            self.mt[i] = self.mt[(i + 397) % 624] ^ (y >> 1)
            if y % 2:
                self.mt[i] ^= 2567483615
        self.idx = 0

    def next32(self) -> int:
        if self.idx >= 624:
            self._gen()
        y = self.mt[self.idx]
        self.idx += 1
        y ^= y >> 11
        y ^= (y << 7) & 0x9D2C5680
        y ^= (y << 15) & 0xEFC60000
        y ^= y >> 18
        return y & 0xFFFFFFFF


LCG_LIB = {
    "MINSTD": (16807, 0, 2**31 - 1),
    "ANSI-C": (1103515245, 12345, 2**31),
    "glibc32": (1103515245, 12345, 2**32),
    "MSVC": (214013, 2531011, 2**31),
    "NR": (1664525, 1013904223, 2**32),
    "Borland": (22695477, 1, 2**32),
    "MMIX": (6364136223846793005, 1442695040888963407, 2**64),
}


def gen_indices(kind: str, params: dict, n: int, quota: int):
    """按 kind 产生 quota 个候选序号（含去重语义）。"""
    seed = params["seed"]
    out, seen = [], set()

    def push(i: int) -> bool:
        if i in seen:
            return False
        seen.add(i)
        out.append(i)
        return len(out) == quota

    if kind.startswith("java_"):
        r = JavaRandom(seed)
        while True:
            i = (r.next_int(n) + 1) if kind.endswith("nextint") else (int(r.next_double() * n) + 1)
            if push(i):
                return out
    if kind.startswith("csharp_"):
        r = CSharpRandom(seed)
        while True:
            i = (int(r.sample() * n) + 1) if kind.endswith("sample") else (int(r.sample() * n) + 1)
            if push(i):
                return out
    if kind.startswith("mt_cpp_"):
        r = MT19937InitGenrand(seed)
        while True:
            v = r.next32()
            i = (v % n) + 1 if kind.endswith("mod") else (v * n // (1 << 32)) + 1
            if push(i):
                return out
    if kind.startswith("lcg_"):
        name = kind.split("_", 1)[1]
        a, c, m = LCG_LIB[name]
        x = seed % m
        while True:
            x = (a * x + c) % m
            if push((x * n // m) + 1):
                return out
    if kind.startswith("hash_"):
        algo = kind.split("_")[1]
        h = {"sha256": hashlib.sha256, "sha1": hashlib.sha1, "md5": hashlib.md5}[algo]
        k = 0
        while True:
            for sep in ("", ":", "-"):
                for start in (0, 1):
                    kk = k + start
                    for fmt in (f"{seed}{sep}{kk}", f"{kk}{sep}{seed}", f"{seed}{sep}{kk}{sep}{n}"):
                        d = h(fmt.encode()).digest()
                        v = int.from_bytes(d[:8], "big")
                        cand = [v % n + 1, v * n // (1 << 64) + 1]
                        for i in cand:
                            if push(i):
                                return out
            k += 1
            if k > quota * 20:
                return out
    raise ValueError(kind)


def hash_sortkeys(algo: str, seed: int, n: int, quota: int) -> set[int]:
    """哈希键排序模型：给池中每项算键，取键最小的 quota 个。"""
    h = {"sha256": hashlib.sha256, "md5": hashlib.md5}[algo]
    keys = []
    for j in range(1, n + 1):
        v = int.from_bytes(h(f"{seed}:{j}".encode()).digest()[:8], "big")
        keys.append((v, j))
    keys.sort()
    return {j for _, j in keys[:quota]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="unit")
    ap.add_argument("--periods", nargs="*", default=None)
    a = ap.parse_args()
    files = sorted(f for f in os.listdir(PARSED) if f.endswith(f"_{a.kind}.json"))
    if a.periods:
        files = [f for f in files if any(p in f for p in a.periods)]
    kinds = [f"java_{m}" for m in ("nextint", "nextdouble")] + \
            [f"csharp_{m}" for m in ("sample",)] + \
            [f"mt_cpp_{m}" for m in ("mod", "scale")] + \
            [f"lcg_{nm}" for nm in LCG_LIB] + \
            [f"hash_{al}" for al in ("sha256", "sha1", "md5")]
    try:
        import numpy as np
    except ImportError:
        np = None
    best: list[tuple[int, str, str]] = []
    for f in files:
        row = json.load(open(os.path.join(PARSED, f), encoding="utf-8"))
        facts = row["facts"]
        n = int(facts.get("pool_size") or facts.get("valid_codes"))
        quota = row["count"]
        seed = int(facts["seed"])
        obs = [t[1] for t in row["triples"]]
        obs_set = set(obs)
        chance = quota * quota / n
        line = [f"{f[:-5]:<14} 池={n:<9} 取={quota:<5} 种子={seed:<8} 基线≈{chance:5.2f}"]
        for k in kinds:
            got = gen_indices(k, {"seed": seed}, n, quota)
            ov = len(set(got) & obs_set)
            pos = sum(1 for u, v in zip(got[:30], obs[:30]) if u == v)
            best.append((ov, f[:-5], k))
            if ov > max(8, chance * 4) or pos >= 2:
                line.append(f"★{k}:重合{ov}(同位置{pos})")
        for al in ("sha256", "md5"):
            got = hash_sortkeys(al, seed, n, quota)
            ov = len(got & obs_set)
            best.append((ov, f[:-5], f"hash_sortkeys_{al}"))
            if ov > max(8, chance * 4):
                line.append(f"★hash_sortkeys_{al}:重合{ov}")
        if np is not None:
            for gname, gen in (("np_RandomState", np.random.RandomState(seed)),
                               ("np_default_rng", np.random.default_rng(seed))):
                for mname in ("randint", "scale"):
                    if gname == "np_RandomState":
                        vals = gen.randint(1, n + 1, size=quota * 3) if mname == "randint" else \
                            (gen.random_sample(quota * 3) * n).astype("int64") + 1
                    else:
                        vals = gen.integers(1, n + 1, size=quota * 3) if mname == "randint" else \
                            (gen.random(quota * 3) * n).astype("int64") + 1
                    got, seen = [], set()
                    for v in vals:
                        v = int(v)
                        if v in seen:
                            continue
                        seen.add(v)
                        got.append(v)
                        if len(got) == quota:
                            break
                    ov = len(set(got) & obs_set)
                    best.append((ov, f[:-5], f"{gname}_{mname}"))
                    if ov > max(8, chance * 4):
                        line.append(f"★{gname}_{mname}:重合{ov}")
        print("  ".join(line))
    best.sort(reverse=True)
    print("\n最高重合 TOP10（命中需接近 quota 值）：")
    for ov, p, k in best[:10]:
        print(f"  {ov:5d}  {p:<14} {k}")


if __name__ == "__main__":
    main()
