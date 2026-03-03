#!/bin/bash

af3_input_json=$1
input_dir=$2
prediction_dir=$3
evaluation_dir=$4
gpu_id=$5

PYTHON_PATH="/opt/conda/envs/openfold3/bin/python3"
RUN_OF3="/opt/conda/envs/openfold3/bin/run_openfold"

# Step 1: Convert AF3 JSON to OF3 query JSON
$PYTHON_PATH /algo/preprocess.py --af3_input_json="$af3_input_json" --input_dir="$input_dir"

# Step 2: Run OpenFold3 inference with specified seeds and PAE preset
export CUDA_VISIBLE_DEVICES=$gpu_id

# Auto-confirm any interactive prompts (e.g., for model weight downloads)
yes | $RUN_OF3 predict \
    --query_json "$input_dir/inputs.json" \
    --num_diffusion_samples 5 \
    --runner_yaml /algo/runner.yaml \
    --use_msa_server True \
    --output_dir "$prediction_dir"

# Step 3: Normalize CIFs and generate prediction_reference.csv
$PYTHON_PATH /algo/postprocess.py \
    --input_dir="$input_dir" \
    --prediction_dir="$prediction_dir" \
    --evaluation_dir="$evaluation_dir"
