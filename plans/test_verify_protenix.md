# Implementation Plan - Test and Verify Protenix Pipeline

## 1. 🔍 Analysis & Context
*   **Objective:** Verify the full structure prediction pipeline for the Protenix algorithm, including preprocessing, model inference, and postprocessing.
*   **Affected Files:**
    *   `algorithms/Protenix/preprocess.py`
    *   `algorithms/Protenix/make_predictions.sh`
    *   `algorithms/Protenix/postprocess.py`
    *   `algorithms/Protenix/container.sif` (Apptainer image)
*   **Key Dependencies:**
    *   Apptainer (Singularity)
    *   NVIDIA GPU (GH200 Hopper)
    *   Standard AF3 input JSON format
*   **Risks/Unknowns:**
    *   Inference time: Running 5 seeds x 5 samples (25 predictions) for a single target may take significant time (15-30 minutes).
    *   GPU memory usage: Protenix is memory-intensive.

## 2. 📋 Checklist
- [x] Step 1: Dry-run Verification (Static analysis and file checks)
- [x] Step 2: Live Preprocess Verification
- [x] Step 3: Live Pipeline Verification (Inference + Postprocess)
- [x] Step 4: Output Validation (CSV and CIF checks)

## 3. 📝 Step-by-Step Implementation Details

### Step 1: Dry-run Verification
*   **Goal:** Ensure all required files and methods are present without running the container.
*   **Action:**
    *   Run `./algorithms/test_algorithm.sh --algorithm Protenix --dry-run`.
*   **Verification:**
    *   Check for "PASS: Protenix is correctly configured." output.
*   **Status:** ✅ Verified in research and implementation phases.

### Step 2: Live Preprocess Verification
*   **Goal:** Verify that `preprocess.py` correctly converts AF3 JSON to Protenix-native format.
*   **Action:**
    *   The `test_algorithm.sh` script automatically performs this in live mode.
*   **Verification:**
    *   Check for "Live preprocess test PASSED" in the output.
*   **Status:** ✅ Verified. `inputs.json` was correctly created in `examples/outputs/input/Protenix`.

### Step 3: Live Pipeline Verification (Inference + Postprocess)
*   **Goal:** Run the full pipeline inside the Apptainer container on a small test target (`5sbj-assembly1`).
*   **Action:**
    *   Run `./algorithms/test_algorithm.sh --algorithm Protenix --gpu-id 0`.
*   **Verification:**
    *   Check for "Live prediction test PASSED: prediction_reference.csv with 25 prediction rows."
*   **Status:** ✅ Verified. Successfully ran full inference for 5 seeds x 5 samples. Fixed `torch_shm_manager` issue by setting `TMPDIR` in `make_predictions.sh`.

### Step 4: Output Validation
*   **Goal:** Manually verify the contents of the generated outputs if needed (though `test_algorithm.sh` does basic checks).
*   **Action:**
    *   Check `outputs/evaluation/Protenix/prediction_reference.csv` for 25 rows and correct columns.
    *   Inspect one of the `_postprocessed.cif` files to ensure B-factors are 0 and occupancy is 1.
*   **Verification:**
    *   Success criteria met as per `PIPELINE_TESTING.md`.
*   **Status:** ✅ Verified. `prediction_reference.csv` contains 25 rows with correct columns. `ranking_score` matches JSON source. CIF files have `B_iso_or_equiv` = 0 and `occupancy` = 1.

## 4. 🧪 Testing Strategy
*   **Unit Tests:** N/A (covered by `test_algorithm.sh` static checks).
*   **Integration Tests:** The `test_algorithm.sh` script serves as the integration test suite for the algorithm pipeline.
*   **Manual Verification:**
    1. Verify GPU availability with `nvidia-smi`.
    2. Check that `algorithms/Protenix/container.sif` exists.
    3. Run the live test script.

## 5. ✅ Success Criteria
*   [x] All required pipeline files exist and have correct method signatures.
*   [x] `preprocess.py` creates `inputs.json` in the Protenix-native format.
*   [x] Full inference pipeline runs without error on `5sbj-assembly1.json`.
*   [x] `prediction_reference.csv` is generated with 25 rows.
*   [x] All 25 predicted CIF files are normalized correctly.
