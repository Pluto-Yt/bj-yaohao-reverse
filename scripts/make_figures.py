#!/usr/bin/env python3
"""生成文章配图（PNG，公众号可直接上传）。

输出：
  figures/fig1-审计卡方.png        31 期抽样均匀性 χ²(10)，附 5% 临界线
  figures/fig2-负对照.png          正确种子 / 种子+1 / 随机基线 三柱对比
  figures/fig3-子序列对齐.png      2026-P1 个人摇号：公示中签在生成流中的位置 + 被跳过的抽取
  figures/fig4-单位摇号精确复现.png 16 期单位摇号：复现重合数 vs 指标数
"""
from __future__ import annotations

import json
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prng_zoo import CSharpRandom  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG = os.path.join(ROOT, "figures")
os.makedirs(FIG, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "Hiragino Sans GB", "Songti SC"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 144
BLUE, ORANGE, GREY, RED = "#2b6cb0", "#dd6b20", "#a0aec0", "#c53030"


def audit_rows() -> list[dict]:
    """从 audit.py 的输出日志读取（若无则现算）。"""
    log = os.path.join(ROOT, "outputs", "04-audit.log")
    rows = []
    if os.path.exists(log):
        for line in open(log, encoding="utf-8").read().splitlines()[1:]:
            m = re.match(r"(\S+)\s+(\S+)\s+\S+\s+(\d+)\s+\d+\s+\S+\s+([\d.]+)\s+([\d.]+)", line)
            if m:
                rows.append(dict(period=m.group(1), kind=m.group(2), pool=int(m.group(3)),
                                 chi2=float(m.group(4)), p=float(m.group(5))))
    return rows


def fig1(rows: list[dict]) -> None:
    rows = sorted(rows, key=lambda r: (r["period"], r["kind"]))
    labels = [f"{r['period']}\n{'单位' if r['kind'] == 'unit' else '个人'}" for r in rows]
    vals = [r["chi2"] for r in rows]
    colors = [ORANGE if r["kind"] == "unit" else BLUE for r in rows]
    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.bar(range(len(vals)), vals, color=colors, width=0.7)
    ax.axhline(18.31, color=RED, ls="--", lw=1.2)
    ax.text(len(vals) - 0.5, 18.9, "5% 临界值 18.31", color=RED, ha="right", fontsize=9)
    ax.set_xticks(range(len(vals)))
    ax.set_xticklabels(labels, fontsize=6.2)
    ax.set_ylabel("χ²(10)")
    ax.set_title("31 期摇号的抽样均匀性检验：全部远低于临界值（蓝=家庭和个人，橙=单位）", fontsize=11)
    ax.set_ylim(0, 21)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig1-审计卡方.png"))
    plt.close(fig)


def fig2(verif: list[dict]) -> None:
    picks = [r for r in verif if r["period"] in ("2024-P1", "2025-P2", "2026-P1") and r["kind"] == "person"]
    picks += [r for r in verif if r["period"] in ("2023-P2", "2026-P1") and r["kind"] == "unit"]
    labels = [f"{r['period']}\n{'单位' if r['kind'] == 'unit' else '个人'}" for r in picks]
    x = range(len(picks))
    w = 0.26
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar([i - w for i in x], [r["overlap"] for r in picks], w, label="正确种子：重合数", color=BLUE)
    ax.bar(list(x), [r["control_overlap"] for r in picks], w, label="负对照：种子 +1", color=ORANGE)
    ax.bar([i + w for i in x], [r["chance"] for r in picks], w, label="随机基线", color=GREY)
    for i, r in enumerate(picks):
        ax.text(i - w, r["overlap"] * 1.02, f"{r['overlap']}/{r['quota']}", ha="center", fontsize=7.5)
    ax.set_yscale("log")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("中签序号重合数（对数轴）")
    ax.set_title("同一期数据：换对种子就完全复现，换错种子立刻跌回随机水平", fontsize=11)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig2-负对照.png"))
    plt.close(fig)


def fig3(period: str = "2026-P1") -> None:
    row = json.load(open(os.path.join(ROOT, "data", "parsed", f"{period}_person.json"), encoding="utf-8"))
    f = row["facts"]
    n = int(f.get("pool_size") or f.get("valid_codes"))
    quota, seed = row["count"], int(f["seed"])
    obs = [t[1] for t in row["triples"]]
    obs_set = set(obs)
    r = CSharpRandom(seed)
    stream, seen = [], set()
    while len(stream) < quota * 3:
        i = int(r.sample() * n) + 1
        if i in seen:
            continue
        seen.add(i)
        stream.append(i)
    pos = {v: k for k, v in enumerate(stream)}
    last = max(pos[w] for w in obs)
    cov = stream[: last + 1]
    xs_w = [pos[w] for w in obs][:1200]
    ys_w = [obs.index(w) if False else i for i, w in enumerate(obs)][:1200]
    fig, ax = plt.subplots(figsize=(8.4, 4.6))
    ax.scatter(xs_w, ys_w, s=3, color=BLUE, label="公示中签序号（按抽取顺序）")
    gaps = [(k, v) for k, v in enumerate(cov) if v not in obs_set]
    ax.scatter([k for k, _ in gaps], [0] * len(gaps), s=10, color=ORANGE, marker="v",
               label=f"被跳过的抽取（共 {len(gaps)} 次）")
    ax.set_xlabel("在生成流中的位置（次）")
    ax.set_ylabel("公示名次")
    ax.set_title(f"{period} 家庭和个人摇号：公示名单是生成流的严格子序列（前 1200 名）", fontsize=11)
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig3-子序列对齐.png"))
    plt.close(fig)


def fig4(verif: list[dict]) -> None:
    rows = sorted([r for r in verif if r["kind"] == "unit"], key=lambda r: (r["period"]))
    labels = [r["period"] for r in rows]
    x = range(len(rows))
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.bar([i - 0.2 for i in x], [r["quota"] for r in rows], 0.4, label="指标数（公示）", color=GREY)
    ax.bar([i + 0.2 for i in x], [r["overlap"] for r in rows], 0.4, label="复现重合数", color=BLUE)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=7.5, rotation=45, ha="right")
    ax.set_ylabel("个数")
    ax.set_title("16 期单位摇号：逐位精确复现（重合数 = 指标数，且顺序一致）", fontsize=11)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig4-单位摇号精确复现.png"))
    plt.close(fig)


def main() -> None:
    rows = audit_rows()
    verif = json.load(open(os.path.join(ROOT, "data", "verification.json"), encoding="utf-8"))
    if rows:
        fig1(rows)
    fig2(verif)
    fig3()
    fig4(verif)
    for name in sorted(os.listdir(FIG)):
        print("  ", name, os.path.getsize(os.path.join(FIG, name)) // 1024, "KB")


if __name__ == "__main__":
    main()
