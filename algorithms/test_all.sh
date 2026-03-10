TOTAL_START=$(date +%s)

run_timed() {
    local algo=$1
    local start=$(date +%s)
    echo "=== Starting: $algo at $(date) ==="
    bash /projects/u5fx/hussian-simulation-hdx/projects/FoldBench/algorithms/test_algorithm.sh --algorithm $algo
    local end=$(date +%s)
    echo "=== Finished: $algo in $((end - start))s ==="
}

run_timed alphafold3
run_timed boltz2
run_timed openfold3
run_timed helixfold3
run_timed Protenix

TOTAL_END=$(date +%s)
echo "=== Total time: $((TOTAL_END - TOTAL_START))s ==="