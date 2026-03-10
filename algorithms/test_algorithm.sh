#!/bin/bash

# Takes argument --algorithm <algorithm_name> to specify which algorithm/folder to test.
# Input jsons for testing can be found in /projects/u5fx/hussian-simulation-hdx/projects/FoldBench/examples/job_jsons
# Example folder: /projects/u5fx/hussian-simulation-hdx/projects/FoldBench/examples

set -e

# Parse arguments
ALGO=""
DRY_RUN=0
GPU_ID=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --algorithm)
            ALGO="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --gpu-id)
            GPU_ID="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

# Validate algorithm name provided
if [[ -z "$ALGO" ]]; then
    echo "Usage: $0 --algorithm <algorithm_name> [--dry-run] [--gpu-id <id>]"
    exit 1
fi

# Set algorithm directory with canonicalized paths
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ALGO_DIR="$SCRIPT_DIR/$ALGO"
JOB_JSONS_DIR="$SCRIPT_DIR/../examples/job_jsons"

# Check if algorithm directory exists
if [[ ! -d "$ALGO_DIR" ]]; then
    echo "ERROR: Algorithm directory not found: $ALGO_DIR"
    exit 1
fi

# Initialize errors array
declare -a ERRORS

# Temp file variables for live mode
TEMP_JSON=""
TEMP_INPUT_DIR=""
TEMP_PRED_JSON=""
TEMP_OUTPUT_ROOT_DIR=""
TEMP_OVERLAY_IMG=""

# Cleanup function for temp files
cleanup() {
    [[ -n "$TEMP_JSON" && -f "$TEMP_JSON" ]] && rm -f "$TEMP_JSON" || true
    [[ -n "$TEMP_INPUT_DIR" && -d "$TEMP_INPUT_DIR" ]] && rm -rf "$TEMP_INPUT_DIR" || true
    [[ -n "$TEMP_PRED_JSON" && -f "$TEMP_PRED_JSON" ]] && rm -f "$TEMP_PRED_JSON" || true
    [[ -n "$TEMP_OUTPUT_ROOT_DIR" && -d "$TEMP_OUTPUT_ROOT_DIR" ]] && rm -rf "$TEMP_OUTPUT_ROOT_DIR" || true
    [[ -n "$TEMP_OVERLAY_IMG" && -f "$TEMP_OVERLAY_IMG" ]] && rm -f "$TEMP_OVERLAY_IMG" || true
}
trap cleanup EXIT

# Required files to check
REQUIRED_FILES=("container.def" "preprocess.py" "make_predictions.sh" "postprocess.py")

# Check for required files
for FILE in "${REQUIRED_FILES[@]}"; do
    if [[ ! -f "$ALGO_DIR/$FILE" ]]; then
        ERRORS+=("ERROR: Required file missing: $FILE")
    fi
done

# Check for container.sif (mode-dependent: warning for dry-run, error for live)
if [[ ! -f "$ALGO_DIR/container.sif" ]]; then
    if [[ "$DRY_RUN" -eq 0 ]]; then
        ERRORS+=("ERROR: container.sif not found. Run build_apptainer_images.sh to build it.")
    else
        echo "WARNING: container.sif not found. Run build_apptainer_images.sh to build it."
    fi
fi

# Static analysis: check for required classes/methods (only if Python files exist)
if [[ -f "$ALGO_DIR/preprocess.py" ]]; then
    if ! grep -q "class PreProcess" "$ALGO_DIR/preprocess.py"; then
        ERRORS+=("ERROR: preprocess.py missing class PreProcess")
    fi
    if ! grep -q "def preprocess" "$ALGO_DIR/preprocess.py"; then
        ERRORS+=("ERROR: preprocess.py missing def preprocess")
    fi
fi

if [[ -f "$ALGO_DIR/postprocess.py" ]]; then
    if ! grep -q "class PostProcess" "$ALGO_DIR/postprocess.py"; then
        ERRORS+=("ERROR: postprocess.py missing class PostProcess")
    fi
    if ! grep -q "def postprocess" "$ALGO_DIR/postprocess.py"; then
        ERRORS+=("ERROR: postprocess.py missing def postprocess")
    fi
fi

# Live preprocess test (if not in dry-run mode)
if [[ "$DRY_RUN" -eq 0 ]]; then
    echo "Running live preprocess test for $ALGO..."
    if [[ ! -d "$JOB_JSONS_DIR" ]]; then
        ERRORS+=("ERROR: Job JSON directory not found: $JOB_JSONS_DIR")
    else
        TEMP_JSON="$(mktemp /tmp/foldbench_combined_XXXXXX.json)"
        TEMP_INPUT_DIR="$(mktemp -d /tmp/foldbench_input_XXXXXX)"

        # Combine individual job JSONs into one array
        if python3 -c "
import json, glob, sys
files = sorted(glob.glob('$JOB_JSONS_DIR/*.json'))
if not files: sys.exit(1)
combined = [json.load(open(f)) for f in files]
json.dump(combined, open('$TEMP_JSON', 'w'))
"; then
            # Run PreProcess via subprocess with command-line arguments
            if python3 "$ALGO_DIR/preprocess.py" --af3_input_json "$TEMP_JSON" --input_dir "$TEMP_INPUT_DIR" > /dev/null 2>&1; then
                OUTPUT_COUNT=$(find "$TEMP_INPUT_DIR" -maxdepth 1 -type f | wc -l)
                if [[ "$OUTPUT_COUNT" -lt 1 ]]; then
                    ERRORS+=("ERROR: preprocess produced no output files")
                else
                    echo "Live preprocess test PASSED: $OUTPUT_COUNT output file(s) created."
                fi
            else
                ERRORS+=("ERROR: preprocess.py raised an exception or exited non-zero")
            fi
        else
            ERRORS+=("ERROR: Failed to combine job JSON files from $JOB_JSONS_DIR")
        fi
    fi
fi

# Live prediction test (if not in dry-run mode)
if [[ "$DRY_RUN" -eq 0 ]]; then
    TEST_TARGET="7fwl-assembly1"
    echo "Running live prediction test for $ALGO (target: $TEST_TARGET)..."
    SMALLEST_JSON="$JOB_JSONS_DIR/${TEST_TARGET}.json"

    if [[ ! -f "$SMALLEST_JSON" ]]; then
        ERRORS+=("ERROR: Test target not found: $SMALLEST_JSON")
    elif [[ ! -f "$ALGO_DIR/container.sif" ]]; then
        echo "WARNING: Skipping prediction test: container.sif not found."
    else
        TEMP_PRED_JSON="$(mktemp /tmp/foldbench_pred_XXXXXX.json)"
        TEMP_OUTPUT_ROOT_DIR="$(mktemp -d /tmp/foldbench_pred_out_XXXXXX)"
        TEMP_OVERLAY_IMG="/tmp/foldbench_overlay_$$.img"

        # Wrap single target as a JSON array
        python3 -c "
import json
json.dump([json.load(open('$SMALLEST_JSON'))], open('$TEMP_PRED_JSON', 'w'))
"
        HELIX_ENV=""
        if [[ "$ALGO" == "helixfold3" ]]; then
            HELIX_ENV="HF3_SEEDS=42 HF3_DIFF_BATCH_SIZE=1 HF3_INFER_TIMES=1 "
        fi
        # Create output subdirectories (mirroring /algo/outputs layout)
        mkdir -p "$TEMP_OUTPUT_ROOT_DIR/input/$ALGO"
        mkdir -p "$TEMP_OUTPUT_ROOT_DIR/prediction/$ALGO"
        mkdir -p "$TEMP_OUTPUT_ROOT_DIR/evaluation/$ALGO"

        # Create writable sparse overlay
        if apptainer overlay create --size 2048 --sparse "$TEMP_OVERLAY_IMG"; then
            if apptainer exec --nv \
                --overlay "$TEMP_OVERLAY_IMG" \
                -B "$TEMP_PRED_JSON:/algo/alphafold3_inputs.json" \
                -B "$TEMP_OUTPUT_ROOT_DIR:/algo/outputs" \
                -B "$ALGO_DIR:/algo" \
                -B "/projects/u5fx/hussian-simulation-hdx/projects/ATLAS_MSA/AF3_weights:/projects/u5fx/hussian-simulation-hdx/projects/ATLAS_MSA/AF3_weights" \
                "$ALGO_DIR/container.sif" \
                bash -c "chmod +x /algo/make_predictions.sh && cd /algo && ${HELIX_ENV}./make_predictions.sh \
                    /algo/alphafold3_inputs.json \
                    /algo/outputs/input/$ALGO \
                    /algo/outputs/prediction/$ALGO \
                    /algo/outputs/evaluation/$ALGO \
                    $GPU_ID"; then

                PRED_CSV="$TEMP_OUTPUT_ROOT_DIR/evaluation/$ALGO/prediction_reference.csv"
                if [[ ! -f "$PRED_CSV" ]]; then
                    ERRORS+=("ERROR: prediction pipeline produced no prediction_reference.csv")
                else
                    PRED_ROWS=$(( $(wc -l < "$PRED_CSV") - 1 ))
                    if [[ "$PRED_ROWS" -lt 1 ]]; then
                        ERRORS+=("ERROR: prediction_reference.csv has no prediction rows")
                    else
                        echo "Live prediction test PASSED: prediction_reference.csv with $PRED_ROWS prediction rows."
                    fi
                fi
            else
                ERRORS+=("ERROR: apptainer exec failed (make_predictions.sh exited non-zero)")
            fi
        else
            ERRORS+=("ERROR: Failed to create Apptainer overlay image")
        fi
    fi
fi

# Report results
if [[ ${#ERRORS[@]} -eq 0 ]]; then
    echo "PASS: $ALGO is correctly configured."
    exit 0
else
    for ERROR in "${ERRORS[@]}"; do
        echo "$ERROR"
    done
    exit 1
fi
