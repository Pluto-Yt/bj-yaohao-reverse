#!/usr/bin/env python3
"""方案A：跨期统计审计 —— 摇号结果是否真的像无偏随机抽样。

检验项（每期每类）：
  1. 一致性：解析条数 == 公示「指标配置总数」；序号/基数序号/申请编码三者无重复。
  2. 均匀性：池按等宽分箱（10 箱与 100 箱）的卡方检验（Wilson–Hilferty 近似的上尾 p 值）。
  3. 相关性：中签池序号与申请编码数值的 Spearman 相关（应≈0）。
  4. 抽取顺序：按「序号」列的相邻差 (i_{k+1}-i_k) mod N 的 10 箱卡方（真随机应均匀）。
  5. 游程：相邻差分正负号游程数是否符合随机期望。

用法：python3 scripts/audit.py [--json]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARSED = os.path.join(ROOT, "data", "parsed")


def chi2_p(chi2: float, df: int) -> float:
    """上尾 p 值的 Wilson–Hilferty 正态近似（df≥3 足够准）。"""
    if df <= 0:
        return float("nan")
    z = ((chi2 / df) ** (1 / 3) - (1 - 2 / (9 * df))) / math.sqrt(2 / (9 * df))
    return 0.5 * math.erfc(z / math.sqrt(2))


def chi2_uniform(values: list[int], n_bins: int, lo: int, hi: int) -> tuple[float, float]:
    counts = [0] * n_bins
    span = hi - lo + 1
    for v in values:
        b = min(n_bins - 1, (v - lo) * n_bins // span)
        counts[b] += 1
    exp = len(values) / n_bins
    chi2 = sum((c - exp) ** 2 / exp for c in counts)
    return chi2, chi2_p(chi2, n_bins - 1)


def spearman(xs: list[int], ys: list[int]) -> float:
    def ranks(v: list[int]) -> list[float]:
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def runs_test(signs: list[int]) -> tuple[int, float]:
    runs = 1 + sum(1 for a, b in zip(signs, signs[1:]) if a != b)
    n1, n2 = signs.count(1), signs.count(-1)
    if n1 < 2 or n2 < 2:
        return runs, float("nan")
    mu = 2 * n1 * n2 / (n1 + n2) + 1
    var = (2 * n1 * n2 * (2 * n1 * n2 - n1 - n2)) / ((n1 + n2) ** 2 * (n1 + n2 - 1))
    z = (runs - mu) / math.sqrt(var)
    return runs, 0.5 * math.erfc(abs(z) / math.sqrt(2))


def audit_row(row: dict) -> dict:
    n = int(row["facts"].get("pool_size") or row["facts"].get("valid_codes") or 0)
    quota = int(row["facts"].get("quota", 0) or 0)
    triples = row["triples"]
    xu = [t[0] for t in triples]
    idx = [t[1] for t in triples]
    code = [int(t[2]) for t in triples]

    out: dict = {
        "period": row["period"], "kind": row["kind_slug"],
        "seed": row["facts"].get("seed"), "pool": n, "quota": quota, "count": row["count"],
        "count_ok": row["count"] == quota,
        "uniq_xu": len(set(xu)) == len(xu), "uniq_idx": len(set(idx)) == len(idx),
        "uniq_code": len(set(code)) == len(code),
    }
    if n and idx:
        c10, p10 = chi2_uniform(idx, 10, 1, n)
        c100, p100 = chi2_uniform(idx, 100, 1, n)
        out.update(chi2_10=c10, p_10=p10, chi2_100=c100, p_100=p100,
                   idx_min=min(idx), idx_max=max(idx))
        out["spearman_code"] = spearman(idx, code)
        diffs = [(idx[i + 1] - idx[i]) % n for i in range(len(idx) - 1)]
        dc, dp = chi2_uniform(diffs, 10, 0, n - 1)
        out.update(chi2_diff=dc, p_diff=dp)
        signs = [1 if d > n // 2 else -1 for d in diffs if d != n // 2]
        runs, pruns = runs_test(signs)
        out.update(runs=runs, runs_expected=2 * len(signs) * 0.5 if signs else 0, p_runs=pruns)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    a = ap.parse_args()
    rows = []
    for f in sorted(os.listdir(PARSED)):
        if f.endswith(".json"):
            rows.append(json.load(open(os.path.join(PARSED, f), encoding="utf-8")))
    rows.sort(key=lambda r: (r["period"], r["kind"]))
    results = [audit_row(r) for r in rows]
    if a.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
        return
    print(f"{'期次':<9}{'类别':<6}{'种子':>8}{'池大小':>11}{'条数':>6} {'一致性':<5}"
          f"{'χ²(10)':>8}{'p':>7}{'与编码ρ':>9}{'差分χ²':>8}{'p':>7}{'游程p':>8}")
    for r in results:
        if not r.get("pool"):
            print(f"{r['period']:<9}{r['kind']:<6}{str(r['seed']):>8}{'?':>11}{r['count']:>6} 解析失败")
            continue
        print(f"{r['period']:<9}{r['kind']:<6}{str(r['seed']):>8}{r['pool']:>11}{r['count']:>6} "
              f"{'✓' if r['count_ok'] else '✗':<5}{r['chi2_10']:>8.2f}{r['p_10']:>7.3f}"
              f"{r['spearman_code']:>9.4f}{r['chi2_diff']:>8.2f}{r['p_diff']:>7.3f}{r['p_runs']:>8.3f}")


if __name__ == "__main__":
    main()
