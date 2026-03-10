# Implementation Plan - Fix missing ml_collections in helixfold3 container

## 1. 🔍 Analysis & Context
*   **Objective:** Fix `ModuleNotFoundError: No module named 'ml_collections'` when running `helixfold3` by updating its Apptainer definition file to explicitly install `ml-collections` and other missing dependencies.
*   **Affected Files:** `algorithms/helixfold3/container.def`
*   **Key Dependencies:** `ml_collections`, `absl-py`, `biopython`, `immutabledict`, `jsonschema`, `posebusters`
*   **Risks/Unknowns:** Rebuilding the container image may take time and requires `apptainer` with `fakeroot` or root privileges. If some packages fail to install via mamba, they might need pip.

## 2. 📋 Checklist
- [ ] Update `algorithms/helixfold3/container.def`: Add missing dependencies to `mamba create`.
- [ ] Update `algorithms/helixfold3/container.def`: Ensure `pip install -r requirements.txt` is more robust.
- [ ] Update `algorithms/helixfold3/container.def`: Add verification step for `ml_collections`.
- [ ] Verification: Instructions for the user to rebuild the image and re-run the test.

## 3. 📝 Step-by-Step Implementation Details

### Step 1: Update `container.def` with explicit dependencies
*   **Goal:** Ensure `ml_collections` and other core dependencies are installed during environment creation.
*   **Action:**
    *   Modify `algorithms/helixfold3/container.def`: Add `ml_collections`, `absl-py`, `biopython`, `immutabledict`, `jsonschema` to the `/conda/bin/mamba create` command.
    *   Add `posebusters` via `pip` after the `mamba create` step.
*   **Verification:** Check the `container.def` file for the added packages.

### Step 2: Robustify `requirements.txt` installation
*   **Goal:** Make sure the build fails if critical requirements are not met, or at least provides clearer output.
*   **Action:**
    *   Modify `algorithms/helixfold3/container.def`: Remove the `|| echo "Some requirements could not be installed"` and let it fail if `pip install -r /tmp/requirements_fixed.txt` fails, OR add `ml-collections` explicitly to the pip install list to ensure it's there.
*   **Verification:** Review the build logic in `container.def`.

### Step 3: Add verification in container build
*   **Goal:** Ensure `ml_collections` is actually importable at the end of the build.
*   **Action:**
    *   Modify `algorithms/helixfold3/container.def`: Add `import ml_collections` to the `=== Verification ===` section.
*   **Verification:** Check the verification section in `container.def`.

## 4. 🧪 Testing Strategy
*   **Manual Verification:**
    1.  Rebuild the image: `apptainer build --fakeroot algorithms/helixfold3/container.sif algorithms/helixfold3/container.def`
    2.  Run the test: `bash algorithms/test_algorithm.sh --algorithm helixfold3`
*   **Success Metric:** The live prediction test for `helixfold3` should no longer fail with `ModuleNotFoundError: No module named 'ml_collections'`.

## 5. ✅ Success Criteria
*   The `container.def` file includes `ml_collections` (or `ml-collections`) in its installation steps.
*   The `=== Verification ===` section in `container.def` checks for `ml_collections`.
*   The user can successfully run the test after rebuilding the image.
