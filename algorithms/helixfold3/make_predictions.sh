#!/bin/bash

set -euo pipefail

af3_input_json="${1:-}"
input_dir="${2:-}"
prediction_dir="${3:-}"
evaluation_dir="${4:-}"
gpu_id="${5:-0}"

if [[ -z "$af3_input_json" || -z "$input_dir" || -z "$prediction_dir" || -z "$evaluation_dir" ]]; then
    echo "Usage: $0 <af3_input_json> <input_dir> <prediction_dir> <evaluation_dir> [gpu_id]"
    exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-/conda/envs/helixfold/bin/python}"
HF3_SCRIPT="${HF3_SCRIPT:-/opt/helixfold3/inference.py}"
HF3_MODEL_NAME="${HF3_MODEL_NAME:-allatom_demo}"
HF3_PRECISION="${HF3_PRECISION:-fp32}"
HF3_INFER_TIMES="${HF3_INFER_TIMES:-1}"
HF3_DIFF_BATCH_SIZE="${HF3_DIFF_BATCH_SIZE:-5}"
HF3_MAX_TEMPLATE_DATE="${HF3_MAX_TEMPLATE_DATE:-2021-09-30}"

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "ERROR: Python binary not executable: $PYTHON_BIN"
    exit 1
fi
if [[ ! -f "$HF3_SCRIPT" ]]; then
    echo "ERROR: HelixFold3 inference script not found: $HF3_SCRIPT"
    exit 1
fi

# Ensure conda env's libstdc++ takes precedence over Ubuntu 22.04 system libs
# This fixes the GLIBCXX_3.4.32 ImportError by loading conda-forge libstdc++ first
export LD_LIBRARY_PATH="/conda/envs/helixfold/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

# Inject BioPython >= 1.80 compatibility: Bio.Data.SCOPData was removed, re-create it
if ! "$PYTHON_BIN" -c "from Bio.Data import SCOPData" 2>/dev/null; then
    "$PYTHON_BIN" - << 'PY'
import pathlib, Bio
bio_data = pathlib.Path(Bio.__file__).parent / "Data"
(bio_data / "SCOPData.py").write_text(
    "# Compatibility shim: Bio.Data.SCOPData removed in BioPython >= 1.80\n"
    "from Bio.Data.IUPACData import protein_letters_3to1\n"
)
PY
fi

# Ensure tqdm is available (missing from container)
"$PYTHON_BIN" -c "import tqdm" 2>/dev/null || \
    "$PYTHON_BIN" -m pip install --quiet tqdm

mkdir -p "$input_dir" "$prediction_dir" "$evaluation_dir"

# Convert AF3 JSON list to per-target HelixFold3 native JSON files.
"$PYTHON_BIN" ./preprocess.py \
    --af3_input_json "$af3_input_json" \
    --input_dir "$input_dir"

if [[ -n "${HF3_INIT_MODEL:-}" ]]; then
    INIT_MODEL="$HF3_INIT_MODEL"
else
    INIT_MODEL="$(find /opt/helixfold3 -type f -name '*.pdparams' 2>/dev/null | head -n 1 || true)"
fi
if [[ -z "$INIT_MODEL" || ! -f "$INIT_MODEL" ]]; then
    echo "ERROR: HelixFold3 model checkpoint not found. Set HF3_INIT_MODEL or include *.pdparams in the container."
    exit 1
fi

if [[ -n "${HF3_CCD_PREPROCESSED_PATH:-}" ]]; then
    CCD_PREPROCESSED_PATH="$HF3_CCD_PREPROCESSED_PATH"
else
    CCD_PREPROCESSED_PATH="$(find /opt/helixfold3 -type f -name 'ccd_preprocessed_etkdg.pkl.gz' 2>/dev/null | head -n 1 || true)"
fi
if [[ -z "$CCD_PREPROCESSED_PATH" || ! -f "$CCD_PREPROCESSED_PATH" ]]; then
    echo "ERROR: CCD preprocessed file not found. Set HF3_CCD_PREPROCESSED_PATH or include ccd_preprocessed_etkdg.pkl.gz in the container."
    exit 1
fi

# inference.py currently requires database/template args even when bypassed via NO_MSA.
PLACEHOLDER_DIR="$prediction_dir/.hf3_placeholders"
mkdir -p "$PLACEHOLDER_DIR/template_mmcif"
touch "$PLACEHOLDER_DIR/db.fasta" "$PLACEHOLDER_DIR/pdb_seqres.txt" "$PLACEHOLDER_DIR/obsolete.dat"

if [[ -n "${HF3_SEEDS:-}" ]]; then
    SEEDS="$(echo "$HF3_SEEDS" | tr ',' ' ')"
else
SEEDS="$("$PYTHON_BIN" - <<PY
import json
with open("$af3_input_json", "r") as f:
    payload = json.load(f)
if isinstance(payload, dict):
    payload = [payload]
seeds = payload[0].get("modelSeeds", [42, 66, 101, 2024, 8888]) if payload else [42, 66, 101, 2024, 8888]
print(" ".join(str(int(seed)) for seed in seeds))
PY
)"
fi

shopt -s nullglob
target_jsons=("$input_dir"/*.json)
if [[ ${#target_jsons[@]} -eq 0 ]]; then
    echo "ERROR: preprocess produced no target JSON files in $input_dir"
    exit 1
fi

for target_json in "${target_jsons[@]}"; do
    target_name="$(basename "$target_json" .json)"
    for seed in $SEEDS; do
        seed_output_dir="$prediction_dir/$target_name/seed_$seed"
        mkdir -p "$seed_output_dir"

        echo "Running HelixFold3 target=$target_name seed=$seed gpu=$gpu_id"
        CUDA_VISIBLE_DEVICES="$gpu_id" "$PYTHON_BIN" "$HF3_SCRIPT" \
            --input_json "$target_json" \
            --output_dir "$seed_output_dir" \
            --seed "$seed" \
            --infer_times "$HF3_INFER_TIMES" \
            --diff_batch_size "$HF3_DIFF_BATCH_SIZE" \
            --precision "$HF3_PRECISION" \
            --model_name "$HF3_MODEL_NAME" \
            --init_model "$INIT_MODEL" \
            --ccd_preprocessed_path "$CCD_PREPROCESSED_PATH" \
            --preset reduced_dbs \
            --msa_dir "$input_dir" \
            --reduced_bfd_database_path "$PLACEHOLDER_DIR/db.fasta" \
            --uniprot_database_path "$PLACEHOLDER_DIR/db.fasta" \
            --pdb_seqres_database_path "$PLACEHOLDER_DIR/pdb_seqres.txt" \
            --uniref90_database_path "$PLACEHOLDER_DIR/db.fasta" \
            --mgnify_database_path "$PLACEHOLDER_DIR/db.fasta" \
            --rfam_database_path "$PLACEHOLDER_DIR/db.fasta" \
            --template_mmcif_dir "$PLACEHOLDER_DIR/template_mmcif" \
            --obsolete_pdbs_path "$PLACEHOLDER_DIR/obsolete.dat" \
            --max_template_date "$HF3_MAX_TEMPLATE_DATE"
    done
done

"$PYTHON_BIN" ./postprocess.py \
    --input_dir "$input_dir" \
    --prediction_dir "$prediction_dir" \
    --evaluation_dir "$evaluation_dir"
