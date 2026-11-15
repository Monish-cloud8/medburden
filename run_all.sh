#!/usr/bin/env bash
# MedBurden: tests, sample images, RxNav cache, evaluation (+ LLM-only baseline if a key is set), held-out check.
# Results: results/metrics.json, report.md, comparison.csv/.png, unmatched.csv, beers_misses.csv, holdout/
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
echo "== 1/7 Unit tests";                     $PY -m pytest -q tests
echo "== 2/7 Eval photos + demo photos";      $PY scripts/make_eval_images.py >/dev/null && (cd scripts && $PY make_demo_images.py)
echo "== 3/7 Warm RxNav cache";               $PY scripts/warm_cache.py || echo "(RxNav warm-up skipped)"
echo "== 4/7 Brand map vs RxNav";             $PY scripts/check_brand_map.py || echo "(brand map check skipped)"
if [ -n "${ANTHROPIC_API_KEY:-}${OPENAI_API_KEY:-}" ]; then
  echo "== 5/7 Evaluation + LLM-only baseline (key found)"
else
  echo "== 5/7 Evaluation (no ANTHROPIC_API_KEY / OPENAI_API_KEY set: LLM-only baseline will be skipped)"
fi
$PY scripts/evaluate.py "$@"
echo "== 6/7 Held-out check (brands not in the local map)"
$PY scripts/evaluate.py --eval-dir tests/eval_set_holdout --out-dir results/holdout "$@" | tail -3
echo "== 7/7 Answer-key check sheet";         $PY scripts/make_verify.py
echo
echo "Done. See results/report.md and results/comparison.csv.  Launch the app:  streamlit run app/app.py"
