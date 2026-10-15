#!/usr/bin/env python3
"""复现与验证：北京市小客车指标摇号的抽取算法。

已由公开公示数据反推并验证的算法
--------------------------------
  1. 现场抽出的「指标配置种子数」作为 .NET Framework `System.Random` 的种子；
  2. 循环调用 `Sample()` 得到 u∈[0,1)，取  序号 = floor(u × 池大小) + 1
     （池大小 = 公示的「基数序号总数」；单位摇号与 2020 年个人摇号为「有效编码总数」）；
  3. 若该序号已中签（或其申请编码已中签），丢弃并继续抽，直到达到「指标配置总数」；
  4. 公示表按抽取顺序排列。

验证口径
--------
  单位摇号（每个申请单位只有一个序号 ⇒ 去重即等价）: 要求集合与顺序 **完全一致**；
  个人摇号（一个申请编码有多个基数序号 ⇒ 需要池文件才能逐位复现）:
     要求 (a) 公示集合 ⊆ 生成流；(b) 公示序列是生成流的严格子序列；(c) 集合重合率 ≫ 随机基线。
  负对照：把种子换成 seed+1，重合率应回落到随机基线。

用法：python3 scripts/recover.py [--kind unit|person] [--periods ...]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prng_zoo import CSharpRandom  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARSED = os.path.join(ROOT, "data", "parsed")


def draw_stream(seed: int, n: int, count: int) -> list[int]:
    """按算法产生 count 个「互不重复的池序号」（等价于去重跳过语义）。"""
    r = CSharpRandom(seed)
    out, seen = [], set()
    guard = count * 50
    while len(out) < count and guard > 0:
        guard -= 1
        i = int(r.sample() * n) + 1
        if i in seen:
            continue
        seen.add(i)
        out.append(i)
    return out


def is_subsequence(needle: list[int], haystack: list[int]) -> bool:
    it = iter(haystack)
    return all(any(x == y for y in it) for x in needle)


def check(period: str, kind: str) -> dict:
    row = json.load(open(os.path.join(PARSED, f"{period}_{kind}.json"), encoding="utf-8"))
    f = row["facts"]
    n = int(f.get("pool_size") or f.get("valid_codes"))
    quota, seed = row["count"], int(f["seed"])
    obs = [t[1] for t in row["triples"]]
    obs_set = set(obs)
    stream = draw_stream(seed, n, quota * 4 if kind == "person" else quota)
    ctrl = draw_stream(seed + 1, n, quota)
    res = {
        "period": period, "kind": kind, "pool": n, "quota": quota, "seed": seed,
        "exact": stream[:quota] == obs,
        "overlap": len(set(stream[:quota]) & obs_set),
        "contained": not (obs_set - set(stream)),
        "subsequence": is_subsequence(obs, stream),
        "control_overlap": len(set(ctrl) & obs_set),
        "chance": round(quota * quota / n, 2),
    }
    if kind == "person":
        pos = {v: i for i, v in enumerate(stream)}
        last = max(pos[w] for w in obs)
        res["draws_used"] = last + 1
        res["discarded"] = sum(1 for v in stream[: last + 1] if v not in obs_set)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default=None, choices=[None, "unit", "person"])
    ap.add_argument("--periods", nargs="*", default=None)
    a = ap.parse_args()
    kinds = [a.kind] if a.kind else ["unit", "person"]
    rows = []
    for kind in kinds:
        for f in sorted(os.listdir(PARSED)):
            if not f.endswith(f"_{kind}.json"):
                continue
            period = f[: -len(f"_{kind}.json")]
            if a.periods and period not in a.periods:
                continue
            rows.append(check(period, kind))
    print(f"{'期次':<9}{'类别':<7}{'池大小':>11}{'取':>7}{'种子':>8}  {'精确复现':<9}"
          f"{'重合':>7}{'包含':>6}{'子序列':>7}{'跳过':>6}{'负对照':>7}{'基线':>6}")
    for r in rows:
        print(f"{r['period']:<9}{r['kind']:<7}{r['pool']:>11}{r['quota']:>7}{r['seed']:>8}  "
              f"{'✔' if r['exact'] else '—':<9}{r['overlap']:>7}{'✔' if r['contained'] else '✘':>6}"
              f"{'✔' if r['subsequence'] else '✘':>7}{r.get('discarded', 0):>6}"
              f"{r['control_overlap']:>7}{r['chance']:>6}")
    ok_unit = [r for r in rows if r["kind"] == "unit" and r["exact"]]
    ok_person = [r for r in rows if r["kind"] == "person" and r["contained"] and r["subsequence"]]
    print(f"\n单位摇号精确复现 {len(ok_unit)}/{sum(1 for r in rows if r['kind']=='unit')} 期；"
          f"个人摇号包含+子序列验证通过 {len(ok_person)}/{sum(1 for r in rows if r['kind']=='person')} 期")
    json.dump(rows, open(os.path.join(ROOT, "data", "verification.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
