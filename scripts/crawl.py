#!/usr/bin/env python3
"""抓取北京市小客车指标「普通指标配置结果」公示。

流程：公布栏分页 -> 各期结果页 -> (配置事实 + 公示 PDF 链接)
产出：data/index.json   [{period, kind, title, url, seed, pool_size, quota, configured_at, pdf}]
只做公开数据抓取，不登录、不接触个人隐私。
"""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys

BASE = "https://xkczb.jtw.beijing.gov.cn"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "html")
os.makedirs(RAW, exist_ok=True)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"


def fetch(url: str, path: str) -> str:
    """带缓存的 curl 抓取，返回页面文本。"""
    if os.path.exists(path) and os.path.getsize(path) > 500:
        return open(path, encoding="utf-8", errors="ignore").read()
    r = subprocess.run(
        ["curl", "-sL", "-m", "40", "-A", UA, "-o", path, "-w", "%{http_code}", url],
        capture_output=True, text=True,
    )
    code = r.stdout.strip()
    if code != "200" or not os.path.exists(path):
        print(f"  !! HTTP {code} {url}", file=sys.stderr)
        return ""
    return open(path, encoding="utf-8", errors="ignore").read()


def text_of(page: str) -> str:
    """去脚本/样式后转纯文本（保留换行，便于按行取词）。"""
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", "\n", t)
    return html.unescape(t)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def collect_listing() -> dict[str, str]:
    """遍历公布栏 1..31 页，收集「XX配置YYYY年第N期配置结果」链接。"""
    found: dict[str, str] = {}
    for i in range(1, 32):
        url = f"{BASE}/jggb/index.html" if i == 1 else f"{BASE}/jggb/index_{i}.html"
        page = fetch(url, os.path.join(RAW, f"list_{i:02d}.html"))
        if not page:
            continue
        for href, title in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>([^<]{4,90})</a>', page):
            title = norm(html.unescape(title))
            if re.search(r"普通指标配置\d{4}年第\d期配置结果", title):
                if href.startswith("/"):
                    href = BASE + href
                found[href] = title
        print(f"  列表页 {i:02d}: 累计 {len(found)} 条")
    return found


def parse_result(url: str, title: str) -> dict:
    key = re.search(r"/(\d+)/(\d+)_1\.html", url)
    stem = key.group(2) if key else re.sub(r"\W+", "_", url)
    page = fetch(url, os.path.join(RAW, f"page_{stem}.html"))
    if not page:
        return {}
    t = text_of(page)
    flat = norm(t)

    def grab(label: str) -> str:
        m = re.search(label + r"[:：]?\s*([0-9][0-9:\.\- ]{2,30})", flat)
        return m.group(1).strip() if m else ""

    seed = grab("指标配置种子数") or grab("配置种子数") or grab("种子数")
    pool = grab("基数序号总数")
    quota = grab("指标配置总数")
    when = grab("配置时间")

    pdfs = [h if h.startswith("http") else BASE + h
            for h in re.findall(r'href="([^"]+\.pdf)"', page, flags=re.I)]
    period = re.search(r"(\d{4})年第(\d)期", title)
    kind = "单位" if "单位" in title else "家庭和个人"
    return {
        "period": f"{period.group(1)}-P{period.group(2)}" if period else "",
        "kind": kind,
        "title": title,
        "url": url,
        "seed": int(re.sub(r"\D", "", seed) or 0),
        "pool_size": int(re.sub(r"\D", "", pool) or 0),
        "quota": int(re.sub(r"\D", "", quota) or 0),
        "configured_at": norm(when),
        "pdf": pdfs[0] if pdfs else "",
    }


def main() -> None:
    print("== 1/2 遍历公布栏")
    listing = collect_listing()
    print(f"== 2/2 解析 {len(listing)} 个结果页")
    rows = []
    for url, title in sorted(listing.items(), key=lambda kv: kv[1], reverse=True):
        row = parse_result(url, title)
        if row:
            rows.append(row)
            print(f"  {row['period']:8s} {row['kind']:6s} seed={row['seed']:<8d} "
                  f"pool={row['pool_size']:<10d} quota={row['quota']:<5d} pdf={'有' if row['pdf'] else '无'}")
    out = os.path.join(ROOT, "data", "index.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print(f"写出 {out}（{len(rows)} 条）")


if __name__ == "__main__":
    main()
