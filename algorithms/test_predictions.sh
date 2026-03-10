#!/bin/bash
# this script tests all prediction targets in examples/job_jsons
# and checks that outputs are in the expected format in examples/outputs

set -uo pipefail

ALGO=""
GPU_ID=0
DRY_RUN=0

usage() {
    echo "Usage: $0 --algorithm <algorithm_name> [--gpu-id <id>] [--dry-run]"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --algorithm)
            ALGO="${2:-}"
            shift 2
            ;;
        --gpu-id)
            GPU_ID="${2:-0}"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "WARNING: Unknown argument '$1' ignored."
            shift
            ;;
    esac
done

if [[ -z "$ALGO" ]]; then
    usage
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ALGO_DIR="$SCRIPT_DIR/$ALGO"
JOB_JSONS_DIR="$REPO_ROOT/examples/job_jsons"
OUTPUT_ROOT="$REPO_ROOT/examples/outputs"
WEIGHTS_DIR="/projects/u5fx/hussian-simulation-hdx/projects/ATLAS_MSA/AF3_weights"

declare -a ERRORS
declare -a TEMP_FILES
TEMP_OVERLAY_IMG=""

cleanup() {
    for f in "${TEMP_FILES[@]:-}"; do
        [[ -f "$f" ]] && rm -f "$f" || true
    done
    [[ -n "$TEMP_OVERLAY_IMG" && -f "$TEMP_OVERLAY_IMG" ]] && rm -f "$TEMP_OVERLAY_IMG" || true
}
trap cleanup EXIT

if [[ ! -d "$ALGO_DIR" ]]; then
    echo "ERROR: Algorithm directory not found: $ALGO_DIR"
    exit 1
fi

REQUIRED_FILES=("container.def" "preprocess.py" "make_predictions.sh" "postprocess.py")
for FILE in "${REQUIRED_FILES[@]}"; do
    [[ -f "$ALGO_DIR/$FILE" ]] || ERRORS+=("ERROR: Required file missing: $ALGO_DIR/$FILE")
done

if [[ ! -d "$JOB_JSONS_DIR" ]]; then
    ERRORS+=("ERROR: job_jsons directory not found: $JOB_JSONS_DIR")
fi

mapfile -t JOB_JSON_FILES < <(find "$JOB_JSONS_DIR" -maxdepth 1 -type f -name "*.json" | sort)
if [[ ${#JOB_JSON_FILES[@]} -eq 0 ]]; then
    ERRORS+=("ERROR: No JSON targets found in: $JOB_JSONS_DIR")
fi

if [[ "$DRY_RUN" -eq 0 && ! -f "$ALGO_DIR/container.sif" ]]; then
    ERRORS+=("ERROR: container.sif not found: $ALGO_DIR/container.sif")
fi

if [[ "$DRY_RUN" -eq 0 && ! -d "$OUTPUT_ROOT" ]]; then
    mkdir -p "$OUTPUT_ROOT"/{input,prediction,evaluation} || ERRORS+=("ERROR: Failed to create output root: $OUTPUT_ROOT")
fi

if [[ ${#ERRORS[@]} -gt 0 ]]; then
    printf "%s\n" "${ERRORS[@]}"
    exit 1
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "DRY-RUN PASS: static checks passed for '$ALGO'."
    exit 0
fi

if ! command -v apptainer >/dev/null 2>&1; then
    echo "ERROR: apptainer command not found."
    exit 1
fi

TEMP_OVERLAY_IMG="/tmp/foldbench_test_predictions_overlay_$$.img"
if ! apptainer overlay create --size 4096 --sparse "$TEMP_OVERLAY_IMG"; then
    echo "ERROR: Failed to create Apptainer overlay image."
    exit 1
fi

echo "Running prediction tests for algorithm '$ALGO' on ${#JOB_JSON_FILES[@]} target(s)..."

for JOB_JSON in "${JOB_JSON_FILES[@]}"; do
    TARGET="$(basename "$JOB_JSON" .json)"
    echo "==> Testing target: $TARGET"

    WRAPPED_JSON="$(mktemp /tmp/foldbench_${ALGO}_${TARGET}_XXXXXX.json)"
    TEMP_FILES+=("$WRAPPED_JSON")

    if ! python3 - <<PY
import json
src = "$JOB_JSON"
dst = "$WRAPPED_JSON"
with open(src, "r") as f:
    obj = json.load(f)
with open(dst, "w") as f:
    json.dump([obj], f)
PY
    then
        ERRORS+=("ERROR [$TARGET]: Failed to wrap JSON into list format")
        continue
    fi

    HOST_INPUT_DIR="$OUTPUT_ROOT/input/$ALGO/$TARGET"
    HOST_PRED_DIR="$OUTPUT_ROOT/prediction/$ALGO/$TARGET"
    HOST_EVAL_DIR="$OUTPUT_ROOT/evaluation/$ALGO/$TARGET"
    mkdir -p "$HOST_INPUT_DIR" "$HOST_PRED_DIR" "$HOST_EVAL_DIR"

    if ! apptainer exec --nv \
        --overlay "$TEMP_OVERLAY_IMG" \
        -B "$WRAPPED_JSON:/algo/alphafold3_inputs.json" \
        -B "$OUTPUT_ROOT:/algo/outputs" \
        -B "$ALGO_DIR:/algo" \
        -B "$WEIGHTS_DIR:$WEIGHTS_DIR" \
        "$ALGO_DIR/container.sif" \
        bash -c "chmod +x /algo/make_predictions.sh && cd /algo && ./make_predictions.sh \
            /algo/alphafold3_inputs.json \
            /algo/outputs/input/$ALGO/$TARGET \
            /algo/outputs/prediction/$ALGO/$TARGET \
            /algo/outputs/evaluation/$ALGO/$TARGET \
            $GPU_ID"
    then
        ERRORS+=("ERROR [$TARGET]: apptainer exec failed (make_predictions.sh exited non-zero)")
        continue
    fi

    if [[ "$(find "$HOST_INPUT_DIR" -type f | wc -l)" -lt 1 ]]; then
        ERRORS+=("ERROR [$TARGET]: preprocess produced no files in $HOST_INPUT_DIR")
        continue
    fi

    CSV_PATH="$HOST_EVAL_DIR/prediction_reference.csv"
    if [[ ! -f "$CSV_PATH" ]]; then
        ERRORS+=("ERROR [$TARGET]: missing prediction_reference.csv at $CSV_PATH")
        continue
    fi

    if ! python3 - <<PY
import csv, os, sys
csv_path = "$CSV_PATH"
target = "$TARGET"
output_root = "$OUTPUT_ROOT"

required = ["pdb_id", "seed", "sample", "ranking_score", "prediction_path"]

def resolve_exists(path):
    if os.path.exists(path):
        return True
    prefix = "/algo/outputs/"
    if path.startswith(prefix):
        mapped = os.path.join(output_root, path[len(prefix):])
        return os.path.exists(mapped)
    return False

with open(csv_path, newline="") as f:
    reader = csv.DictReader(f)
    fields = reader.fieldnames or []
    missing = [c for c in required if c not in fields]
    if missing:
        print(f"Missing required columns: {missing}")
        sys.exit(1)
    rows = list(reader)

if len(rows) != 25:
    print(f"Expected 25 rows, found {len(rows)}")
    sys.exit(1)

pdb_ids = {r.get("pdb_id", "").strip() for r in rows}
if pdb_ids != {target}:
    print(f"Unexpected pdb_id values: {sorted(pdb_ids)} (expected only '{target}')")
    sys.exit(1)

seed_to_samples = {}
for r in rows:
    try:
        seed = str(int(float(str(r["seed"]).strip())))
        sample = int(float(str(r["sample"]).strip()))
    except Exception:
        print("Non-numeric seed/sample detected")
        sys.exit(1)

    if sample < 0 or sample > 4:
        print(f"Sample out of range [0,4]: {sample}")
        sys.exit(1)

    seed_to_samples.setdefault(seed, set()).add(sample)

    p = str(r.get("prediction_path", "")).strip()
    if not p:
        print("Empty prediction_path found")
        sys.exit(1)
    if not resolve_exists(p):
        print(f"prediction_path does not exist: {p}")
        sys.exit(1)

if len(seed_to_samples) != 5:
    print(f"Expected 5 unique seeds, found {len(seed_to_samples)}: {sorted(seed_to_samples.keys())}")
    sys.exit(1)

for s, samples in seed_to_samples.items():
    if samples != {0,1,2,3,4}:
        print(f"Seed {s} does not have samples 0..4: {sorted(samples)}")
        sys.exit(1)

print("CSV format validation passed.")
PY
    then
        ERRORS+=("ERROR [$TARGET]: prediction_reference.csv format validation failed")
        continue
    fi

    echo "PASS [$TARGET]"
done

if [[ ${#ERRORS[@]} -eq 0 ]]; then
    echo "PASS: all targets completed and validated for '$ALGO'."
    exit 0
fi

printf "%s\n" "${ERRORS[@]}"
exit 1