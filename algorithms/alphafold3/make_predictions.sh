#!/bin/bash

af3_input_json=$1
input_dir=$2
prediction_dir=$3
evaluation_dir=$4
gpu_id=$5

PYTHON_PATH="/alphafold3_venv/bin/python3"

# Split combined JSON list into individual per-target JSON files
$PYTHON_PATH ./preprocess.py --af3_input_json="$af3_input_json" --input_dir="$input_dir"

# Run AlphaFold3 inference
# MSAs are pre-computed in the input JSON, so --run_data_pipeline=false
export CUDA_VISIBLE_DEVICES=$gpu_id

$PYTHON_PATH /app/alphafold/run_alphafold.py \
    --input_dir="$input_dir" \
    --output_dir="$prediction_dir" \
    --model_dir="/projects/u5fx/hussian-simulation-hdx/projects/ATLAS_MSA/AF3_weights" \
    --num_diffusion_samples=5 \
    --num_recycles=10 \
    --run_data_pipeline=false \
    --gpu_device="$gpu_id" \
    --flash_attention_implementation=xla

# Normalize CIF outputs and generate prediction_reference.csv
$PYTHON_PATH ./postprocess.py \
    --input_dir="$input_dir" \
    --prediction_dir="$prediction_dir" \
    --evaluation_dir="$evaluation_dir"
