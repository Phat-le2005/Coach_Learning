#!/usr/bin/env bash
# Run with bash, not sh: bash scripts/run_kaggle.sh all /kaggle/working/comer_hme500_config.json
set -euo pipefail

LAB_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
export PYTHONUNBUFFERED=1
cd "$LAB_DIR"

usage() {
  cat <<'HELP'
Usage:
  bash scripts/run_kaggle.sh setup
  bash scripts/run_kaggle.sh train CONFIG.json [--resume /path/last.pt] [--qa]
  bash scripts/run_kaggle.sh test OUTPUT_DIR [--sync-only]
  bash scripts/run_kaggle.sh all CONFIG.json [--resume /path/last.pt]

setup: install dependencies, unit tests, download/verify official CoMER checkpoint.
train: baseline + fine-tune + validation + W&B + evidence ZIP (no test).
test: evaluate selected best.pt; --sync-only uploads an existing test record.
all: setup + train + final test. Set RUN_FINAL_TEST=0 to keep test held out.
Credentials: WANDB_API_KEY inherited from Kaggle's Python os.environ.
PYTHON_BIN can select an existing Python interpreter; CUDA torch is not replaced.
HELP
}

setup() {
  "$PYTHON_BIN" -m pip install -q -r "$LAB_DIR/requirements.txt"
  "$PYTHON_BIN" -m hme_comer.check_runtime
  "$PYTHON_BIN" -m unittest discover -s "$LAB_DIR/tests" -v
  "$PYTHON_BIN" -m hme_comer.fetch_upstream
}

ACTION="${1:-help}"
if (( $# )); then shift; fi
case "$ACTION" in
  help|-h|--help) usage ;;
  setup)
    if (( $# )); then usage >&2; exit 2; fi
    setup
    ;;
  train)
    if (( $# < 1 )); then usage >&2; exit 2; fi
    CONFIG_PATH="$1"; shift
    "$PYTHON_BIN" -m hme_comer.train --config "$CONFIG_PATH" "$@"
    ;;
  test)
    if (( $# < 1 )); then usage >&2; exit 2; fi
    OUTPUT_DIR="$1"; shift
    "$PYTHON_BIN" -m hme_comer.final_test --output "$OUTPUT_DIR" "$@"
    ;;
  all)
    if (( $# < 1 )); then usage >&2; exit 2; fi
    CONFIG_PATH="$1"; shift
    if [[ "${RUN_FINAL_TEST:-1}" != 0 && "${RUN_FINAL_TEST:-1}" != 1 ]]; then
      printf '%s\n' 'RUN_FINAL_TEST must be 0 or 1.' >&2; exit 2
    fi
    for argument in "$@"; do
      if [[ "$argument" == --qa && "${RUN_FINAL_TEST:-1}" == 1 ]]; then
        printf '%s\n' 'QA cannot run final test. Set RUN_FINAL_TEST=0.' >&2; exit 2
      fi
    done
    setup
    "$PYTHON_BIN" -m hme_comer.train --config "$CONFIG_PATH" "$@"
    if [[ "${RUN_FINAL_TEST:-1}" == 1 ]]; then
      OUTPUT_DIR="$("$PYTHON_BIN" -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["output"])' "$CONFIG_PATH")"
      DEVICE="$("$PYTHON_BIN" -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("device","cuda:0"))' "$CONFIG_PATH")"
      "$PYTHON_BIN" -m hme_comer.final_test --output "$OUTPUT_DIR" --device "$DEVICE"
    fi
    ;;
  *) usage >&2; exit 2 ;;
esac
