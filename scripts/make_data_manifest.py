#!/usr/bin/env python3
"""生成数据快照清单 docs/DATA.md（文件名、来源、大小、SHA-256、关键事实）。

用法：python3 scripts/make_data_manifest.py
"""
from __future__ import annotations

import hashlib
import json
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
os.makedirs(DOCS, exist_ok=True)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def size(path: str) -> str:
    n = os.path.getsize(path)
    return f"{n/1024/1024:.2f} MB" if n >= 1 << 20 else f"{n/1024:.1f} KB"


def main() -> None:
    index = json.load(open(os.path.join(ROOT, "data", "index.json"), encoding="utf-8"))
    rows = {f"{r['period']}_{'unit' if r['kind'] == '单位' else 'person'}": r for r in index}

    lines = [
        "# 数据快照清单",
        "",
        f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        "所有原始文件均来自北京市小客车指标调控管理信息系统公开发布的《配置结果》公示；",
        "本清单给出仓库内留档文件的来源链接、大小与 SHA-256，便于第三方复核与长期引用。",
        "",
        "## 一、公示 PDF（data/pdf/）",
        "",
        "| 期次 | 类别 | 种子数 | 池大小 | 指标数 | 文件大小 | SHA-256（前 16 位） | 来源 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    parsed_dir = os.path.join(ROOT, "data", "parsed")
    for name in sorted(os.listdir(parsed_dir)):
        if not name.endswith(".json"):
            continue
        key = name[:-5]
        row = rows.get(key, {})
        meta = json.load(open(os.path.join(parsed_dir, name), encoding="utf-8"))
        f = meta.get("facts", {})
        pdf = os.path.join(ROOT, "data", "pdf", f"{key}.pdf")
        if not os.path.exists(pdf):
            continue
        lines.append(
            f"| {meta['period']} | {'单位' if meta['kind'] == 'unit' else '家庭和个人'} | "
            f"{f.get('seed','')} | {f.get('pool_size') or f.get('valid_codes','')} | {f.get('quota','')} | "
            f"{size(pdf)} | `{sha256(pdf)[:16]}` | [公示页]({meta.get('url','')}) |"
        )

    refs = os.path.join(ROOT, "data", "refs")
    if os.path.isdir(refs):
        lines += ["", "## 二、参考资料（data/refs/）", "",
                  "| 文件 | 大小 | SHA-256（前 16 位） | 说明 |", "|---|---|---|---|"]
        for name in sorted(os.listdir(refs)):
            p = os.path.join(refs, name)
            note = "GB/T 10111-2008《随机数的产生及其在产品质量抽样检验中的应用程序》标准预览" \
                if "GBT10111" in name else ""
            lines.append(f"| `{name}` | {size(p)} | `{sha256(p)[:16]}` | {note} |")

    lines += [
        "",
        "## 三、解析与验证产物",
        "",
        "| 文件 | 内容 |",
        "|---|---|",
        "| `data/index.json` | 31 期公示索引（期次、类别、种子数、池大小、指标数、公示页与 PDF 链接） |",
        "| `data/parsed/*.json` | 各期解析产物：配置事实 + 全部 `(序号, 摇号基数序号, 申请编码)` 三元组 |",
        "| `data/verification.json` | `scripts/recover.py` 的逐期验证结果（精确复现 / 重合 / 包含 / 子序列 / 负对照） |",
        "",
        "## 四、复核方式",
        "",
        "```bash",
        "python3 scripts/make_data_manifest.py   # 重新生成本清单",
        "python3 scripts/recover.py              # 复现验证（含负对照）",
        "```",
        "",
        "PDF 原件与其 SHA-256 均可与公示页重新下载的文件比对；若发布方更新了文件，哈希会变化，",
        "此时以公示页现行为准，并在 `data/index.json` 中体现新链接。",
        "",
    ]
    out = os.path.join(DOCS, "DATA.md")
    open(out, "w", encoding="utf-8").write("\n".join(lines))
    print(f"写出 {out}（{len(lines)} 行）")


if __name__ == "__main__":
    main()
