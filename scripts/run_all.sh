#!/usr/bin/env bash
# 一键复现：抓取公示 → 下载 PDF → 解析 → 统计审计 → 算法复现验证
# 依赖：python3、curl、pypdf（python3 -m pip install pypdf）
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p outputs

echo "== 1/5 抓取公布栏各期《配置结果》公示链接"
python3 -u scripts/crawl.py | tee outputs/01-crawl.log | tail -3

echo "== 2/5 下载公示 PDF（≥2020 年）"
python3 -u scripts/pipeline.py download --min-year 2020 | tee outputs/02-download.log | tail -3

echo "== 3/5 解析 PDF：配置事实 + 全部中签三元组（含 2014 年回填）"
python3 -u scripts/verify_legacy.py | tee outputs/03b-legacy.log
python3 -u scripts/pipeline.py parse --min-year 2020 | tee outputs/03-parse.log | tail -5

echo "== 4/5 方案A：跨期统计审计"
python3 -u scripts/audit.py | tee outputs/04-audit.log

echo "== 5/5 算法复现与验证（含负对照）"
python3 -u scripts/recover.py | tee outputs/05-recover.log

echo
echo "完成。产物："
echo "  outputs/*.log            各步日志"
echo "  data/index.json          公示索引"
echo "  data/parsed/*.json       各期解析产物"
echo "  data/verification.json   逐期验证结果"
echo
echo "探索性（负结果）脚本可按需运行：hunt.py / hypotheses.py / lcg_index.py / models.py / prng_zoo.py"
