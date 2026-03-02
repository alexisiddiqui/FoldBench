# Implementation Plan - Test Algorithm Script

This plan outlines the implementation of `hussian-simulation-hdx/projects/FoldBench/algorithms/test_algorithm.sh`. This script is designed to validate the integration setup of individual prediction algorithms within the FoldBench platform, ensuring they adhere to the requirements specified in `README.md`.
Output folder: 
hussian-simulation-hdx/projects/FoldBench/test/

## 1. 🔍 Analysis & Context
*   **Objective:** Complete `test_algorithm.sh` to provide a health-check and validation tool for algorithm developers in FoldBench.
*   **Affected Files:**
    *   `hussian-simulation-hdx/projects/FoldBench/algorithms/test_algorithm.sh`
*   **Key Dependencies:**
    *   Bash (core shell)
    *   Apptainer (for container checks)
    *   Grep/Sed (for static code validation)
*   **Risks/Unknowns:**
    *   Ensuring the script is robust enough to handle various algorithm naming conventions.
    *   Static analysis of Python scripts is limited but useful for basic compliance checks.

## 2. 📋 Checklist
- [x] Analyze existing algorithm structures (`Protenix`, `boltz2`, `alphafold3`).
- [ ] Implement robust argument parsing for `--algorithm`.
- [ ] Implement special case handling for `helixfold3` (skip with message).
- [ ] Add existence checks for the four mandatory files: `container.def`, `preprocess.py`, `make_predictions.sh`, and `postprocess.py`.
- [ ] Add existence check for the built container image `container.sif`.
- [ ] Implement basic static validation of `preprocess.py` and `postprocess.py` (checking for required classes and methods).
- [ ] Provide clear, actionable feedback for missing or non-compliant components.
- [ ] Verification on existing algorithms.

## 3. 📝 Step-by-Step Implementation Details

### Step 1: Argument Parsing and Initial Validation
*   **Goal:** Correcty identify the algorithm to test and verify the directory exists.
*   **Action:**
    *   Modify `hussian-simulation-hdx/projects/FoldBench/algorithms/test_algorithm.sh`.
    *   Use a `while` loop with `getopts` or a simple `case` statement to parse `--algorithm <name>`.
    *   Validate that the directory `algorithms/<name>` exists.
*   **Verification:** Run `./test_algorithm.sh --algorithm non_existent` and expect a failure.

### Step 2: Skip Logic for Developing Models
*   **Goal:** Adhere to the requirement of skipping `helixfold3` while it is under development.
*   **Action:**
    *   Check if the provided algorithm name is `helixfold3`.
    *   If so, print "Helixfold3 is still being developed and can be skipped for now." and exit 0.
*   **Verification:** Run `./test_algorithm.sh --algorithm helixfold3` and check output.

### Step 3: Structural Requirements Check
*   **Goal:** Verify the presence of all required integration scripts.
*   **Action:**
    *   Define an array of required files: `container.def`, `preprocess.py`, `make_predictions.sh`, `postprocess.py`.
    *   Loop through the array and check for file existence using `[ -f "$file" ]`.
    *   Accumulate errors and report all missing files at once.
*   **Verification:** Temporarily rename a file in an algorithm folder and run the script.

### Step 4: Container Readiness Check
*   **Goal:** Ensure the Apptainer image is built and ready for execution.
*   **Action:**
    *   Check for `algorithms/<name>/container.sif`.
    *   If missing, print a warning suggesting the use of `./build_apptainer_images.sh`.
*   **Verification:** Check output for an algorithm without a `.sif` file (e.g., `openfold3`).

### Step 5: Interface Compliance Check (Static Analysis)
*   **Goal:** Verify that the Python scripts implement the required classes and methods.
*   **Action:**
    *   For `preprocess.py`: `grep -q "class PreProcess" "$algo_dir/preprocess.py"` and `grep -q "def preprocess" "$algo_dir/preprocess.py"`.
    *   For `postprocess.py`: `grep -q "class PostProcess" "$algo_dir/postprocess.py"` and `grep -q "def postprocess" "$algo_dir/postprocess.py"`.
*   **Verification:** Run against `alphafold3`, `Protenix` or `boltz2`.

## 4. 🧪 Testing Strategy
*   **Unit Tests:** Since this is a bash script, "unit tests" will be manual runs against controlled folder structures.
*   **Integration Tests:**
    *   Run `./test_algorithm.sh --algorithm alphafold3` 
    *   Run `./test_algorithm.sh --algorithm boltz2`.
    *   Run `./test_algorithm.sh --algorithm Protenix`.
*   **Manual Verification:**
    *   Verify that output file structure matches /projects/u5fx/hussian-simulation-hdx/projects/FoldBench/examples/outputs/prediction/
    *   Verify that chains, msas, templates and ligands are all correct in the predictions

## 5. ✅ Success Criteria
*   Script correctly parses arguments.
*   Script identifies all missing required files.
*   Script identifies if `PreProcess` or `PostProcess` classes/methods are missing.
*   Script provides helpful advice on how to fix issues (e.g., build container).
*   Script handles `helixfold3` as a special case.
