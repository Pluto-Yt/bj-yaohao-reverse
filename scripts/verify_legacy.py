#!/usr/bin/env python3
"""把验证窗口前推到 2014 年：下载并解析 2014 年各期公示 PDF，做 .NET Random 复现检验。

2014 年公示的字段名与现在不同（种子数当时叫「指标配置初始值」），列结构相同：
    序号 / 摇号基数序号 / 申请编码
产出与 pipeline.py 一致的 data/parsed/<period>_<kind>.json，因此 recover.py / audit.py 会自动覆盖这些期。

用法：python3 scripts/verify_legacy.py [--years 2014 2015 2016]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(ROOT, "data", "pdf")
OUT_DIR = os.path.join(ROOT, "data", "parsed")
os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"
TRIPLE = re.compile(r"(?<![\d.])(\d{1,7})\s+(\d{1,9})\s+(\d{13})(?!\d)")
FACTS = {
    "seed": re.compile(r"(?:指标配置种子数|指标配置初始值)\s*[:：]\s*(\d+)"),
    "pool_size": re.compile(r"(?:基数序号总数|有效编码总数|有效单位申请编码总数|有效\S*编码总数)\s*[:：]\s*(\d+)"),
    "quota": re.compile(r"(?:指标配置总数|配置单位指标总数|配置指标总数)\s*[:：]\s*(\d+)"),
    "configured_at": re.compile(r"(?:配置时间|实际指标配置时间|指标配置日期)\s*[:：]\s*([0-9]{4}-[0-9]{2}-[0-9]{2}[ 0-9:]*)"),
}
# 2014 年起公示表才有「摇号基数序号」列（官方口径 + 实测确认）
CASES = [
    # (period, kind, pdf_url)
    ("2014-P1", "person", "https://xkczb.jtw.beijing.gov.cn/attachment/2014226/1393383551096.pdf"),
    ("2014-P1", "unit", "https://xkczb.jtw.beijing.gov.cn/attachment/2014226/1393383946708.pdf"),
]


def fetch(url: str, path: str) -> bool:
    if os.path.exists(path) and os.path.getsize(path) > 20000:
        return True
    r = subprocess.run(["curl", "-sL", "-m", "120", "-A", UA, "-o", path, "-w", "%{http_code}", url],
                       capture_output=True, text=True)
    return r.stdout.strip() == "200" and os.path.getsize(path) > 20000


def parse(pdf: str, period: str, kind: str, url: str) -> dict:
    from pypdf import PdfReader
    rd = PdfReader(pdf)
    facts: dict = {}
    triples: list[list[int]] = []
    for i, page in enumerate(rd.pages):
        text = page.extract_text() or ""
        if i == 0:
            for k, rx in FACTS.items():
                m = rx.search(text)
                if m:
                    facts[k] = m.group(1)
        for m in TRIPLE.finditer(text):
            triples.append([int(m.group(1)), int(m.group(2)), m.group(3)])
    row = {"period": period, "kind": kind, "kind_slug": kind, "title": f"{period} {kind}（legacy）",
           "url": url, "pdf": url, "pdf_sha256": hashlib.sha256(open(pdf, "rb").read()).hexdigest(),
           "pages": len(rd.pages), "facts": facts, "count": len(triples), "triples": triples}
    json.dump(row, open(os.path.join(OUT_DIR, f"{period}_{kind}.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    return row


def check(row: dict) -> dict:
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from prng_zoo import CSharpRandom
    f = row["facts"]
    n = int(f.get("pool_size") or 0)
    quota, seed = row["count"], int(f.get("seed") or 0)
    obs = [t[1] for t in row["triples"]]
    obs_set = set(obs)

    def stream(sd: int, count: int) -> list[int]:
        r, out, seen = CSharpRandom(sd), [], set()
        while len(out) < count:
            i = int(r.sample() * n) + 1
            if i in seen:
                continue
            seen.add(i)
            out.append(i)
        return out

    gen = stream(seed, quota * 4 if row["kind"] == "person" else quota)
    ctrl = stream(seed + 1, quota)
    it = iter(gen)
    subseq = all(any(x == o for x in it) for o in obs)
    return {"period": row["period"], "kind": row["kind"], "pool": n, "quota": quota, "seed": seed,
            "exact": gen[:quota] == obs, "overlap": len(set(gen[:quota]) & obs_set),
            "contained": not (obs_set - set(gen)), "subsequence": subseq,
            "control_overlap": len(set(ctrl) & obs_set), "chance": round(quota * quota / n, 2)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", nargs="*", default=None)
    a = ap.parse_args()
    for period, kind, url in CASES:
        if a.cases and f"{period}_{kind}" not in a.cases:
            continue
        pdf = os.path.join(PDF_DIR, f"{period}_{kind}.pdf")
        if not fetch(url, pdf):
            print(f"  ✗ 下载失败 {period} {kind} {url}")
            continue
        row = parse(pdf, period, kind, url)
        res = check(row)
        print(f"  {period} {kind:6s} 池={res['pool']:<9} 取={res['quota']:<6} 种子={res['seed']:<8} "
              f"精确={res['exact']} 重合={res['overlap']}/{res['quota']} 包含={res['contained']} "
              f"子序列={res['subsequence']} 负对照={res['control_overlap']} 基线={res['chance']}")


if __name__ == "__main__":
    main()
