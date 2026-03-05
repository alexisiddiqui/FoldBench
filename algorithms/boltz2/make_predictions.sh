#!/bin/bash

af3_input_json=$1
input_dir=$2
prediction_dir=$3
evaluation_dir=$4
gpu_id=$5

PYTHON_PATH="/boltz_venv/bin/python3"

# Step 1: Convert AF3 JSON to Boltz YAML files
$PYTHON_PATH /algo/preprocess.py --af3_input_json="$af3_input_json" --input_dir="$input_dir"

# Step 2: Extract seeds from AF3 input JSON (modelSeeds field, first entry)
seeds=$($PYTHON_PATH -c "
import json
with open('$af3_input_json') as f:
    data = json.load(f)
seeds = data[0].get('modelSeeds', ['42', '66', '101', '2024', '8888'])
print(' '.join(str(s) for s in seeds))
")

export CUDA_VISIBLE_DEVICES=$gpu_id

# Step 3: Run Boltz inference once per seed (5 diffusion samples per seed)
for seed in $seeds; do
    /boltz_venv/bin/boltz predict "$input_dir" \
        --out_dir "${prediction_dir}/seed_${seed}" \
        --seed $seed \
        --recycling_steps 10 \
        --diffusion_samples 5 \
        --sampling_steps 200 \
        --output_format mmcif \
        --override
done

# Step 4: Normalize CIFs and generate prediction_reference.csv
$PYTHON_PATH /algo/postprocess.py \
    --input_dir="$input_dir" \
    --prediction_dir="$prediction_dir" \
    --evaluation_dir="$evaluation_dir"
