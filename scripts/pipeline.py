#!/usr/bin/env python3
"""北京市小客车指标摇号数据管道：下载公示 PDF -> 解析配置事实与中签明细。

用法：
  python3 scripts/pipeline.py download [--min-year 2020]
  python3 scripts/pipeline.py parse    [--min-year 2020]

产出：
  data/pdf/<period>_<kind>.pdf
  data/parsed/<period>_<kind>.json  {"period","kind","facts":{seed,pool_size,quota,configured_at},
                                     "count":N,"triples":[[序号,基数序号,申请编码],...],"pdf_sha256":...}
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(ROOT, "data", "pdf")
OUT_DIR = os.path.join(ROOT, "data", "parsed")
os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"
KIND = {"家庭和个人": "person", "单位": "unit"}
TRIPLE = re.compile(r"(?<![\d.])(\d{1,7})\s+(\d{1,9})\s+(\d{13})(?!\d)")
FACTS = {
    "seed": re.compile(r"指标配置种子数\s*[:：]\s*(\d+)"),
    "pool_size": re.compile(r"基数序号总数\s*[:：]\s*(\d+)"),
    "valid_codes": re.compile(r"有效编码总数\s*[:：]\s*(\d+)"),
    "quota": re.compile(r"指标配置总数\s*[:：]\s*(\d+)"),
    "configured_at": re.compile(r"配置时间\s*[:：]\s*([0-9]{4}-[0-9]{2}-[0-9]{2}[ 0-9:]*)"),
}


def rows(min_year: int) -> list[dict]:
    data = json.load(open(os.path.join(ROOT, "data", "index.json"), encoding="utf-8"))
    out = []
    for r in data:
        if not r.get("pdf"):
            continue
        y = int(r["period"][:4]) if r.get("period") else 0
        if y and y >= min_year and r["kind"] in KIND:
            r = dict(r, kind_slug=KIND[r["kind"]], year=y)
            out.append(r)
    return sorted(out, key=lambda r: (r["year"], r["period"], r["kind_slug"]), reverse=True)


def pdf_path(r: dict) -> str:
    return os.path.join(PDF_DIR, f"{r['period']}_{r['kind_slug']}.pdf")


def download(r: dict) -> str:
    p = pdf_path(r)
    if os.path.exists(p) and os.path.getsize(p) > 20000:
        return f"cached {os.path.basename(p)}"
    tmp = p + ".part"
    res = subprocess.run(["curl", "-sL", "-m", "120", "-A", UA, "-o", tmp, "-w", "%{http_code}", r["pdf"]],
                         capture_output=True, text=True)
    ok = res.stdout.strip() == "200" and os.path.exists(tmp) and os.path.getsize(tmp) > 20000
    if ok:
        os.replace(tmp, p)
        return f"ok {os.path.basename(p)} {os.path.getsize(p)//1024}KB"
    if os.path.exists(tmp):
        os.remove(tmp)
    return f"FAIL {r['period']} {r['kind_slug']} HTTP {res.stdout.strip()} {r['pdf']}"


def parse_one(r: dict) -> dict | None:
    from pypdf import PdfReader  # 延迟导入，便于 download 子命令不依赖

    p = pdf_path(r)
    if not os.path.exists(p):
        return None
    out_path = os.path.join(OUT_DIR, f"{r['period']}_{r['kind_slug']}.json")
    if os.path.exists(out_path):  # 已有含 valid_codes 的解析结果则跳过
        try:
            old = json.load(open(out_path, encoding="utf-8"))
            if "valid_codes" in old.get("facts", {}):
                return old
        except Exception:
            pass
    digest = hashlib.sha256(open(p, "rb").read()).hexdigest()
    rd = PdfReader(p)
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
    row = {
        "period": r["period"], "kind": r["kind_slug"], "kind_slug": r["kind_slug"],
        "title": r["title"], "url": r["url"],
        "pdf": r["pdf"], "pdf_sha256": digest, "pages": len(rd.pages),
        "facts": facts, "count": len(triples), "triples": triples,
    }
    out = os.path.join(OUT_DIR, f"{r['period']}_{r['kind_slug']}.json")
    json.dump(row, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["download", "parse"])
    ap.add_argument("--min-year", type=int, default=2020)
    ap.add_argument("--jobs", type=int, default=6)
    a = ap.parse_args()
    todo = rows(a.min_year)
    print(f"[{a.step}] {len(todo)} 个文件（≥{a.min_year} 年）")
    if a.step == "download":
        with ThreadPoolExecutor(a.jobs) as ex:
            for msg in ex.map(download, todo):
                print("  ", msg)
        return
    for r in todo:
        row = parse_one(r)
        if not row:
            print(f"   缺 PDF: {r['period']} {r['kind_slug']}")
            continue
        f = row["facts"]
        flag = "" if row["count"] == int(f.get("quota", -1) or -1) else "  <== 数量与总数不符"
        print(f"  {row['period']:8s} {row['kind_slug']:6s} seed={f.get('seed','?'):>8s} "
              f"pool={f.get('pool_size','?'):>10s} quota={f.get('quota','?'):>5s} "
              f"解析={row['count']:<5d}{flag}")


if __name__ == "__main__":
    main()
