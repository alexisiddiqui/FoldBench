# FoldBench Pipeline Testing Guide

## Purpose

This document is a self-contained technical brief for implementing and testing
`preprocess.py`, `postprocess.py`, and `make_predictions.sh` for each
prediction algorithm in the FoldBench benchmark. It provides enough context to
implement or debug these scripts without consulting any other file in the repo.

---

## 1. Repo Overview

**FoldBench** is an all-atom biomolecular structure prediction benchmark
(published Nature Communications 2025). It evaluates structure prediction
algorithms on 1,860 targets spanning 8 interaction and monomer types. Scoring
is performed via DockQ and LDDT.

**Platform:** Linux + Apptainer (Singularity) + NVIDIA GH200 Hopper GPU.
**Repo root:** `/projects/u5fx/hussian-simulation-hdx/projects/FoldBench`

---

## 2. Overall Pipeline Architecture

`run.sh` at the repo root orchestrates the full benchmark. For each algorithm
the pipeline is:

```
run.sh
  └─► apptainer exec container.sif make_predictions.sh \
          /algo/alphafold3_inputs.json \
          /algo/outputs/input/{algo} \
          /algo/outputs/prediction/{algo} \
          /algo/outputs/evaluation/{algo} \
          {gpu_id}
            │
            ├── preprocess.py       ← converts input JSON to algo-native format
            ├── model inference     ← algo-specific CLI command
            └── postprocess.py      ← normalizes CIFs + writes prediction_reference.csv
```

### Directory layout inside the container

All paths are from the container's perspective. The host directory tree is
bind-mounted at `/algo/`:

```
/algo/
  alphafold3_inputs.json          ← combined input JSON (list of all targets)
  preprocess.py
  postprocess.py
  make_predictions.sh
  outputs/
    input/{algo}/                 ← preprocessed per-target input files
    prediction/{algo}/            ← raw model outputs (.cif files)
    evaluation/{algo}/
      prediction_reference.csv   ← REQUIRED final output
```

The bind mounts set up by `test_algorithm.sh` (and by `run.sh`) are:
- `alphafold3_inputs.json` → `/algo/alphafold3_inputs.json`
- `outputs/` host dir → `/algo/outputs`
- `algorithms/{algo}/` → `/algo`

### Exact `apptainer exec` invocation

```bash
apptainer exec --nv \
    --overlay <sparse_overlay.img> \
    -B <input.json>:/algo/alphafold3_inputs.json \
    -B <output_root>:/algo/outputs \
    -B <algo_dir>:/algo \
    <algo_dir>/container.sif \
    bash -c "chmod +x /algo/make_predictions.sh && cd /algo && \
        ./make_predictions.sh \
            /algo/alphafold3_inputs.json \
            /algo/outputs/input/{algo} \
            /algo/outputs/prediction/{algo} \
            /algo/outputs/evaluation/{algo} \
            {gpu_id}"
```

`--nv` enables NVIDIA GPU passthrough. The writable overlay image lets the
container create temporary files without modifying the read-only `.sif`.

### What's baked into the container vs what's bind-mounted

This distinction is critical for understanding when to rebuild the container:

| Item | Source | Notes |
|------|--------|-------|
| Python interpreter (venv / conda env) | **Baked into container** | Created in `%post` during `apptainer build` |
| Installed packages (torch, boltz, biotite, etc.) | **Baked into container** | `pip`/`conda` installs in `%post` |
| Model inference executable | **Baked into container** | e.g. `/boltz_venv/bin/boltz` |
| `preprocess.py` | **Bind-mounted at runtime** | Host file at `$ALGO_DIR`, appears as `/algo/preprocess.py` |
| `postprocess.py` | **Bind-mounted at runtime** | Host file at `$ALGO_DIR`, appears as `/algo/postprocess.py` |
| `make_predictions.sh` | **Bind-mounted at runtime** | Host file at `$ALGO_DIR`, appears as `/algo/make_predictions.sh` |
| `alphafold3_inputs.json` | **Bind-mounted at runtime** | Host JSON wrapped into a single-element list before mounting |
| `outputs/` directory | **Bind-mounted at runtime** | Host directory, written back to host after the run |

**Key implication:** Editing `preprocess.py`, `postprocess.py`, or
`make_predictions.sh` does **not** require rebuilding the container — just
re-run. Only rebuild when `container.def` changes (new packages, tools, or
model installation steps).

---

## 3. Standard Input Format: AF3 JSON

All algorithms receive targets in **AlphaFold3 JSON format**. The combined
input file (`alphafold3_inputs.json`) is a JSON **array** of target objects.
Each algorithm's `preprocess.py` converts this to the algorithm-native format.

### Full field reference

```jsonc
{
  "dialect": "alphafold3",      // always "alphafold3"
  "version": 4,                 // always 4
  "name": "5sbj-assembly1",     // target ID (used as pdb_id throughout)

  "sequences": [
    // ── Protein chain ──────────────────────────────────────────────────────
    {
      "protein": {
        "id": "A",              // chain ID (string or list of strings for homo-oligomers)
        "sequence": "XYCSDCGADASQVRGGYCTNCGASADRIRX",
        "modifications": [
          { "ptmType": "ACE", "ptmPosition": 1  },   // N-terminal cap
          { "ptmType": "AIB", "ptmPosition": 10 },   // non-standard residue
          { "ptmType": "NH2", "ptmPosition": 30 }    // C-terminal cap
        ],
        "unpairedMsa": ">101\nSEQUENCE\n",  // pre-computed MSA (A3M string)
        "pairedMsa": "",
        "templates": []
      }
    },
    // ── Ligand ─────────────────────────────────────────────────────────────
    {
      "ligand": {
        "id": "B",              // chain ID
        "ccdCodes": ["CD"]      // CCD code list (usually one entry)
      }
    },
    // ── RNA chain ──────────────────────────────────────────────────────────
    {
      "rna": {
        "id": "C",
        "sequence": "AGCUAGCUAGCU",
        "modifications": [
          { "modificationType": "PSU", "basePosition": 5 }
        ],
        "unpairedMsa": "",
        "pairedMsa": ""
      }
    },
    // ── DNA chain ──────────────────────────────────────────────────────────
    {
      "dna": {
        "id": ["D", "E"],       // list → homo-dimer
        "sequence": "ATCGATCG",
        "modifications": []
      }
    }
  ],

  "modelSeeds": [42, 66, 101, 2024, 8888],  // ALWAYS these 5 seeds

  "bondedAtomPairs": null,      // null or list of bonded atom pairs
  "userCCD": null               // null or custom CCD dict
}
```

### Key notes
- MSAs are **pre-computed** inside the JSON (`unpairedMsa` / `pairedMsa`).
  Do not run the data pipeline a second time. Pass `--run_data_pipeline=false`
  (AF3) or `--use_msa_server` equivalent where the pre-embedded MSAs are
  forwarded through YAML.
- `modelSeeds` is always `[42, 66, 101, 2024, 8888]`.
- `id` can be a **string** (single chain) or a **list** (homo-oligomer copies).

### Test example
Small test target with one protein chain + one ligand:
`examples/job_jsons/5sbj-assembly1.json`

---

## 4. Required Files Per Algorithm

Each algorithm directory (`algorithms/{algo}/`) must contain:

| File | Key interface | Notes |
|------|--------------|-------|
| `container.def` | Apptainer definition file | Builds `container.sif` |
| `preprocess.py` | `class PreProcess` with `def preprocess(self, af3_input_json, input_dir)` | Called by make_predictions.sh |
| `make_predictions.sh` | bash script, args: `af3_input_json input_dir prediction_dir evaluation_dir gpu_id` | Runs inside container |
| `postprocess.py` | `class PostProcess` with `def postprocess(self, input_dir, prediction_dir, evaluation_dir)` | Called by make_predictions.sh |
| `container.sif` | Built Apptainer image | Required for live runs |

### Interface contracts

**`preprocess.py`**
- CLI: `python preprocess.py --af3_input_json <path> --input_dir <path>`
- Reads the combined AF3 JSON array from `af3_input_json`.
- Writes algo-native input files to `input_dir` (one file per target).
- Must define `class PreProcess` with `def preprocess(self, ...)`.

**`make_predictions.sh`**
- Positional args: `$1`=af3_input_json, `$2`=input_dir, `$3`=prediction_dir,
  `$4`=evaluation_dir, `$5`=gpu_id.
- Calls `preprocess.py`, then model inference, then `postprocess.py`.
- Sets `CUDA_VISIBLE_DEVICES=$gpu_id` before inference.

**`postprocess.py`**
- CLI: `python postprocess.py --input_dir <path> --prediction_dir <path> --evaluation_dir <path>`
- Normalizes CIF files (see §7).
- Writes `prediction_reference.csv` to `evaluation_dir` (see §6).
- Must define `class PostProcess` with `def postprocess(self, ...)`.

---

## 5. Prediction Parameters (standard across all algorithms)

| Parameter | Value |
|-----------|-------|
| Seeds | 42, 66, 101, 2024, 8888 (5 seeds) |
| Diffusion samples per seed | 5 |
| Total predictions per target | 25 (5 seeds × 5 samples) |
| Recycling steps | 10 |
| Diffusion/sampling steps | 200 |

---

## 6. Output: `prediction_reference.csv`

This CSV file is the **primary output** consumed by the FoldBench evaluation
pipeline. It must be written to `evaluation_dir/prediction_reference.csv`.

### Required columns

| Column | Type | Description |
|--------|------|-------------|
| `pdb_id` | str | Target ID from the input JSON `name` field |
| `seed` | int or str | Seed value used for this prediction |
| `sample` | int | **0-indexed** sample number (0–4) |
| `ranking_score` | float | Confidence/ranking score from the model |
| `prediction_path` | str | Absolute path to the **postprocessed** CIF file |

### Expected row count
- 25 rows per target (5 seeds × 5 samples = 25 predictions).
- For a single-target run (e.g., `5sbj-assembly1`), the CSV must have 25 rows.

### `ranking_score` sources by algorithm (see also §10)
- **AF3**: from `{pdb_id}_ranking_scores.csv` in the prediction directory.
- **Boltz2**: from `confidence_{pdb_id}_model_{sample}.json` top-level `confidence_score` key.
- **OpenFold3**: from `{pdb_id}_seed_{seed}_sample_{s}_confidences_aggregated.json` →
  `sample_ranking_score` (fallback: `avg_plddt`).
- **Protenix**: from `{pdb_id}_seed_{seed}_summary_confidence_sample_{sample}.json` →
  `ranking_score`.

---

## 7. CIF Normalization (standard postprocess step)

All `postprocess.py` scripts must normalize CIF files before recording them in
`prediction_reference.csv`. Normalization uses **biotite**:

```python
import biotite.structure.io.pdbx as pdbx

cif_file = pdbx.CIFFile.read(file_path)
block = cif_file.block
atom_site = block.get("atom_site")

# 1. Set occupancy to 1 for all atoms
atom_site["occupancy"] = pdbx.CIFColumn(
    pdbx.CIFData(["1" for _ in range(len(atom_site["group_PDB"]))])
)
# 2. Set B-factor to 0 for all atoms
atom_site["B_iso_or_equiv"] = pdbx.CIFColumn(
    pdbx.CIFData(["0" for _ in range(len(atom_site["group_PDB"]))])
)
# 3. Rebuild _entity category: ATOM records → polymer, HETATM → non-polymer
#    If an entity_id has both ATOM and HETATM records it is polymer.
dict_entity_id = {}
for entity_id, group_pdb in zip(
    atom_site["label_entity_id"].as_array().tolist(),
    atom_site["group_PDB"].as_array().tolist()
):
    if entity_id not in dict_entity_id:
        t = "polymer" if group_pdb == "ATOM" else "non-polymer"
        dict_entity_id[entity_id] = (t, group_pdb)
    else:
        if dict_entity_id[entity_id][1] != group_pdb:
            dict_entity_id[entity_id] = ("polymer", group_pdb)

block["entity"] = pdbx.CIFCategory({
    "id":   list(dict_entity_id.keys()),
    "type": [dict_entity_id[k][0] for k in dict_entity_id.keys()],
})

cif_file.write(new_file_path)
```

**Parallelism:** Use `multiprocessing.Pool` with ~80 % of available CPU cores
and a `tqdm` progress bar. This pattern is the same in all four working
`postprocess.py` scripts.

**Container dependency check:** `biotite`, `pandas`, and `tqdm` must be
installed **inside the container** for `postprocess.py` to function. Verify
they are present in `container.def` before building. For any algorithm where
they are absent, add the following to the `%post` section of `container.def`:
```
pip install biotite pandas tqdm
```

---

## 8. Algorithm-Specific Preprocessing Conversions

### 8.1 AlphaFold3 (`algorithms/alphafold3/`)

Split the combined JSON list into **individual per-target JSON files**. AF3
reads its own format natively.

Output: one `{pdb_id}.json` per target in `input_dir`.

```python
# Pseudo-code
for entry in folding_inputs:
    write(input_dir / f"{entry['name']}.json", entry)
```

### 8.2 Boltz2 (`algorithms/boltz2/`)

Convert each AF3 target to a **Boltz YAML** file (`version: 1`).

Mapping rules:
- `protein` → `protein: {id: ..., sequence: ..., modifications: [{position, ccd}]}`
  - `ptmPosition` → `position`, `ptmType` → `ccd`
- `rna` → `rna: {id: ..., sequence: ..., modifications: [{position, ccd}]}`
  - `basePosition` → `position`, `modificationType` → `ccd`
- `dna` → `dna: {id: ..., sequence: ..., modifications: [{position, ccd}]}`
- `ligand` → `ligand: {id: ..., ccd: <first ccdCode>}` (take `ccdCodes[0]`)

Output: one `{pdb_id}.yaml` per target in `input_dir`.

Example YAML structure:
```yaml
version: 1
sequences:
  - protein:
      id: A
      sequence: XYCSDCGADASQVRGGYCTNCGASADRIRX
      modifications:
        - position: 1
          ccd: ACE
  - ligand:
      id: B
      ccd: CD
```

### 8.3 OpenFold3 (`algorithms/openfold3/`)

Convert all targets into a **single `inputs.json`** file with the structure:
`{"queries": {pdb_id: {"chains": [...]}}}`.

Chain mapping rules:
- `protein`/`rna`/`dna`: `{molecule_type, chain_ids (list), sequence, non_canonical_residues (dict pos→type if any)}`
  - protein modifications: `ptmPosition` → key (str), `ptmType` → value
  - rna/dna modifications: `basePosition` → key (str), `modificationType` → value
- `ligand`: `{molecule_type: "ligand", chain_ids (list), ccd_codes: first code if single else list}`

Output: `input_dir/inputs.json`

Example:
```json
{
  "queries": {
    "5sbj-assembly1": {
      "chains": [
        {
          "molecule_type": "protein",
          "chain_ids": ["A"],
          "sequence": "XYCSDCGADASQVRGGYCTNCGASADRIRX",
          "non_canonical_residues": {"1": "ACE", "10": "AIB", "25": "AIB", "30": "NH2"}
        },
        {
          "molecule_type": "ligand",
          "chain_ids": ["B"],
          "ccd_codes": "CD"
        }
      ]
    }
  }
}
```

### 8.4 Protenix (`algorithms/Protenix/`)

Convert each AF3 target to **Protenix JSON format** and write a single
`input_dir/inputs.json` array.

Mapping rules:
- `protein` → `proteinChain: {sequence, count (len of id list), modifications: [{ptmType: "CCD_{type}", ptmPosition}]}`
- `rna` → `rnaSequence: {sequence, count, modifications: [{modificationType: "CCD_{type}", basePosition}]}`
- `dna` → `dnaSequence: {sequence, count, modifications: [{modificationType: "CCD_{type}", basePosition}]}`
- `ligand` → `ligand: {ligand: "CCD_{code1}_{code2}...", count}`
  - Concatenate all ccdCodes: e.g., `["CD"]` → `"CCD_CD"`, `["ATP", "MG"]` → `"CCD_ATP_MG"`
- Modifications **always** get the `CCD_` prefix prepended.
- Preserve `name` at the top level.

Output: `input_dir/inputs.json` (a JSON array of all targets).

Example:
```json
[
  {
    "name": "5sbj-assembly1",
    "sequences": [
      {
        "proteinChain": {
          "sequence": "XYCSDCGADASQVRGGYCTNCGASADRIRX",
          "count": 1,
          "modifications": [
            {"ptmType": "CCD_ACE", "ptmPosition": 1},
            {"ptmType": "CCD_AIB", "ptmPosition": 10},
            {"ptmType": "CCD_NH2", "ptmPosition": 30}
          ]
        }
      },
      {
        "ligand": {
          "ligand": "CCD_CD",
          "count": 1
        }
      }
    ]
  }
]
```

### 8.5 HelixFold3 (`algorithms/helixfold3/`)

> **Status: integrated.**
>
> `preprocess.py`, `make_predictions.sh`, and `postprocess.py` are implemented.
> The runner uses precomputed-input mode and container-local assets.

HelixFold3 uses its own JSON format. Its inference entrypoint is
`/opt/helixfold3/inference.py` inside the container. Key arguments:
`--input_json`, `--output_dir`, `--seed`, `--infer_times`,
`--ccd_preprocessed_path`, plus database paths.

The input JSON format for HelixFold3 is **different** from AF3 JSON.
Refer to `/opt/helixfold3/README.md` inside the container (or
`algorithms/helixfold3/PaddleHelix/apps/protein_folding/helixfold3/README.md`)
for the expected schema. The `preprocess.py` must convert from AF3 format to
the HelixFold3 native format.

---

## 9. Algorithm-Specific Inference Commands

All commands in this section run **inside the Singularity container**. The
Python interpreter paths below are container-internal paths baked into each
container image — they do not exist on the host system.

### Container Python interpreter paths

| Algorithm | `PYTHON_PATH` in `make_predictions.sh` | Env type |
|-----------|---------------------------------------|----------|
| alphafold3 | `/alphafold3_venv/bin/python3` | venv |
| boltz2 | `/boltz_venv/bin/python3` | venv |
| openfold3 | `/opt/conda/envs/openfold3/bin/python3` | conda |
| Protenix | `/protenix_venv/bin/python` | venv |
| helixfold3 | `/conda/envs/helixfold/bin/python` | conda (also exported as `$PYTHON_BIN`) |

### 9.1 AlphaFold3

```bash
PYTHON_PATH="/alphafold3_venv/bin/python3"

# Preprocess
$PYTHON_PATH ./preprocess.py --af3_input_json="$af3_input_json" --input_dir="$input_dir"

# Inference
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

# Postprocess
$PYTHON_PATH ./postprocess.py \
    --input_dir="$input_dir" \
    --prediction_dir="$prediction_dir" \
    --evaluation_dir="$evaluation_dir"
```

AF3 model weights are at:
`/projects/u5fx/hussian-simulation-hdx/projects/ATLAS_MSA/AF3_weights`

### 9.2 Boltz2

```bash
PYTHON_PATH="/boltz_venv/bin/python3"

# Preprocess
$PYTHON_PATH /algo/preprocess.py --af3_input_json="$af3_input_json" --input_dir="$input_dir"

# Extract seeds from AF3 JSON and loop per seed
seeds=$($PYTHON_PATH -c "
import json
with open('$af3_input_json') as f: data = json.load(f)
seeds = data[0].get('modelSeeds', [42, 66, 101, 2024, 8888])
print(' '.join(str(s) for s in seeds))
")

export CUDA_VISIBLE_DEVICES=$gpu_id
for seed in $seeds; do
    /boltz_venv/bin/boltz predict "$input_dir" \
        --out_dir "${prediction_dir}/seed_${seed}" \
        --seed $seed \
        --use_msa_server \
        --recycling_steps 10 \
        --diffusion_samples 5 \
        --sampling_steps 200 \
        --output_format mmcif \
        --override
done

# Postprocess
$PYTHON_PATH /algo/postprocess.py \
    --input_dir="$input_dir" \
    --prediction_dir="$prediction_dir" \
    --evaluation_dir="$evaluation_dir"
```

Note: `--use_msa_server` is passed but MSAs are pre-embedded in the YAML, so
no server queries are actually made.

### 9.3 OpenFold3

```bash
PYTHON_PATH="/opt/conda/envs/openfold3/bin/python3"
RUN_OF3="/opt/conda/envs/openfold3/bin/run_openfold"

# Preprocess
$PYTHON_PATH /algo/preprocess.py --af3_input_json="$af3_input_json" --input_dir="$input_dir"

# Inference (seeds and recycling configured via runner.yaml)
export CUDA_VISIBLE_DEVICES=$gpu_id
$RUN_OF3 predict \
    --query_json "$input_dir/inputs.json" \
    --num_diffusion_samples 5 \
    --runner_yaml /algo/runner.yaml \
    --use_msa_server True \
    --output_dir "$prediction_dir"

# Postprocess
$PYTHON_PATH /algo/postprocess.py \
    --input_dir="$input_dir" \
    --prediction_dir="$prediction_dir" \
    --evaluation_dir="$evaluation_dir"
```

The `runner.yaml` is at `algorithms/openfold3/runner.yaml` (bound to
`/algo/runner.yaml` inside the container).

OF3 uses **1-indexed** sample numbers in file names (`sample_1` through
`sample_5`) but the CSV stores **0-indexed** samples (0–4).

### 9.4 Protenix

```bash
PYTHON_PATH="/protenix_venv/bin/python"

# Preprocess
$PYTHON_PATH ./preprocess.py --af3_input_json="$af3_input_json" --input_dir="$input_dir"

# Inference (all 5 seeds passed as comma-separated list)
export CUDA_VISIBLE_DEVICES=$gpu_id
$PYTHON_PATH /algo/Protenix/runner/inference.py \
    --seeds 42,66,101,2024,8888 \
    --dump_dir ${prediction_dir} \
    --input_json_path $input_dir/inputs.json \
    --model.N_cycle 10 \
    --sample_diffusion.N_sample 5 \
    --sample_diffusion.N_step 200 \
    --use_msa_server

# Postprocess
$PYTHON_PATH ./postprocess.py \
    --input_dir="$input_dir" \
    --prediction_dir="$prediction_dir" \
    --evaluation_dir="$evaluation_dir"
```

Protenix CIF output path pattern:
`{prediction_dir}/{pdb_id}/seed_{seed}/predictions/{pdb_id}_seed_{seed}_sample_{sample}.cif`
(0-indexed samples 0–4)

### 9.5 HelixFold3

#### Container %environment (pre-set inside the container)

These variables are exported by the container's `%environment` section and are
available automatically when running inside the container — do not redefine
them in `make_predictions.sh`:

```bash
export PATH="/conda/bin:/opt/helixfold3:/conda/envs/helixfold/bin:$PATH"
export PYTHON_BIN="/conda/envs/helixfold/bin/python"
export ENV_BIN="/conda/envs/helixfold/bin"
export OBABEL_BIN="/conda/envs/helixfold/bin"
export CONDA_DEFAULT_ENV="helixfold"
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export OMP_NUM_THREADS=12
# HelixFold3 source is installed at /opt/helixfold3/
# inference.py is at /opt/helixfold3/inference.py
```

HelixFold3 is run per target and per seed, with diffusion batch size 5:

```bash
PYTHON_BIN="${PYTHON_BIN:-/conda/envs/helixfold/bin/python}"
HF3_SCRIPT="/opt/helixfold3/inference.py"

# Preprocess
$PYTHON_BIN /algo/preprocess.py --af3_input_json="$af3_input_json" --input_dir="$input_dir"

# Run inference per seed (5 samples per seed)
export CUDA_VISIBLE_DEVICES=$gpu_id
for seed in 42 66 101 2024 8888; do  # or seeds parsed from AF3 JSON
    $PYTHON_BIN $HF3_SCRIPT \
        --input_json "$input_dir/{target}.json" \
        --output_dir "${prediction_dir}/seed_${seed}" \
        --seed $seed \
        --infer_times 1 \
        --diff_batch_size 5 \
        --ccd_preprocessed_path <container_local_ccd_path> \
        --init_model <container_local_model_path> \
        --preset reduced_dbs
done

# Postprocess
$PYTHON_BIN /algo/postprocess.py \
    --input_dir="$input_dir" \
    --prediction_dir="$prediction_dir" \
    --evaluation_dir="$evaluation_dir"
```

Key HelixFold3 inference arguments (from `inference.py`):
- `--input_json`: path to input JSON (one target at a time or list — confirm format)
- `--output_dir`: output directory
- `--seed INT`: single seed per invocation
- `--infer_times INT`: number of diffusion samples (use 5 for FoldBench)
- `--ccd_preprocessed_path`: required path to CCD preprocessed data
- `--preset`: `full_dbs` or `reduced_dbs`
- Even in precomputed-input mode (`NO_MSA=1`), argparse still requires DB/template
  path flags; pass safe container-local placeholders if those paths are bypassed.

Consult `algorithms/helixfold3/PaddleHelix/apps/protein_folding/helixfold3/inference.py`
for the full argument list and `README.md` for the expected input JSON schema.

---

## 10. Algorithm-Specific Confidence Score Sources

| Algorithm | File | Key |
|-----------|------|-----|
| AF3 | `{prediction_dir}/{pdb_id}/{pdb_id}_ranking_scores.csv` | `ranking_score` column; join on `seed` + `sample` |
| Boltz2 | `{prediction_dir}/seed_{seed}/boltz_results_*/predictions/{pdb_id}/confidence_{pdb_id}_model_{sample}.json` | `confidence_score` |
| OpenFold3 | `{prediction_dir}/{pdb_id}/seed_{seed}/{pdb_id}_seed_{seed}_sample_{s_1indexed}_confidences_aggregated.json` | `sample_ranking_score` (fallback: `avg_plddt`) |
| Protenix | `{prediction_dir}/{pdb_id}/seed_{seed}/predictions/{pdb_id}_seed_{seed}_summary_confidence_sample_{sample}.json` | `ranking_score` |
| HelixFold3 | `{prediction_dir}/{pdb_id}/seed_{seed}/{pdb_id}/{pdb_id}-pred-1-{k}/all_results.json` | `ranking_confidence` |

### AF3 prediction output path pattern
```
{prediction_dir}/{pdb_id}/seed-{seed}_sample-{sample}/{pdb_id}_seed-{seed}_sample-{sample}_model.cif
```
Note the **hyphen** separator (`seed-{seed}_sample-{sample}`) in AF3 paths.

### Boltz2 prediction output path pattern
```
{prediction_dir}/seed_{seed}/boltz_results_{input_dir_name}/predictions/{pdb_id}/{pdb_id}_model_{sample}.cif
```

### OpenFold3 prediction output path pattern
```
{prediction_dir}/{pdb_id}/seed_{seed}/{pdb_id}_seed_{seed}_sample_{s}_model.cif
```
where `s` is **1-indexed** (1–5 in file names, stored as 0-indexed in CSV).

### Protenix prediction output path pattern
```
{prediction_dir}/{pdb_id}/seed_{seed}/predictions/{pdb_id}_seed_{seed}_sample_{sample}.cif
```
where `sample` is **0-indexed** (0–4).

---

## 11. Algorithm Implementation Status

| Algorithm | Container | preprocess.py | make_predictions.sh | postprocess.py | Testing order |
|-----------|-----------|--------------|---------------------|----------------|---------------|
| alphafold3 | ✅ ~90.7 GB | ✅ | ✅ | ✅ | 1 |
| boltz2 | ✅ ~4.8 GB | ✅ | ✅ | ✅ | 2 |
| openfold3 | ⚠️ not yet built | ✅ | ✅ | ✅ | 3 |
| Protenix | ✅ ~13.6 GB | ✅ | ✅ | ✅ | 4 |
| helixfold3 | ✅ built | ✅ | ✅ | ✅ | 5 |

**HelixFold3 runtime notes:**
1. AF3 JSON is converted to HelixFold3 native `entities` JSON per target.
2. Inference runs for seeds 42/66/101/2024/8888 with 5 samples per seed.
3. The runner expects model/CCD assets inside the container.
4. Precomputed-input mode is used (`NO_MSA=1`), avoiding extra host DB dependencies.

---

## 12. Container Build / Rebuild

**Only rebuild the container when `container.def` changes** (i.e., when new
Python packages, compiled tools, or model installation steps need to be added).

`preprocess.py`, `postprocess.py`, and `make_predictions.sh` are **NOT** baked
into the container — they are bind-mounted from the host at runtime. Editing
them takes effect immediately on the next run without any rebuild.

Rebuild triggers:
- Adding a new Python package to `%post` (e.g., `pip install biotite`)
- Changing base image or CUDA version
- Adding new compiled tools or model weights installation steps

### Slurm build scripts
```
/projects/u5fx/hussian-simulation-hdx/_submission/_install/FoldBench/
  build_AF3_container.sh
  build_Boltz2_container.sh
  build_Openfold3_container.sh
  build_Helixfold3_container.sh
  build_PROTEINIX_container.sh
```

Submit with `sbatch`:
```bash
sbatch build_AF3_container.sh
sbatch build_Boltz2_container.sh
# etc.
```

### Local rebuild (if Apptainer available)
```bash
cd algorithms/{algo}/
apptainer build --force container.sif container.def
```

---

## 13. Test Targets

Four AF3 JSON files in `examples/job_jsons/`:

| File | Complexity | Recommended use |
|------|-----------|-----------------|
| `5sbj-assembly1.json` | Small — 1 protein chain + 1 ligand | **Start here** |
| `7fwl-assembly1.json` | Medium | Second test |
| `8e3r-assembly1.json` | Large | Third test |
| `8tuz-assembly1.json` | Very large | Final test |

Always validate with `5sbj-assembly1.json` first before running larger targets.

Each JSON is a **single target object** (not a list). `test_algorithm.sh`
wraps it in a list before passing to `preprocess.py`.

---

## 14. Validation Script

```bash
algorithms/test_algorithm.sh --algorithm <name> [--gpu-id <id>] [--dry-run]
```

**Dry-run mode** (static checks only — no container required):
- Checks that all required files exist (`container.def`, `preprocess.py`,
  `make_predictions.sh`, `postprocess.py`)
- Verifies `class PreProcess` + `def preprocess` are present in `preprocess.py`
- Verifies `class PostProcess` + `def postprocess` are present in `postprocess.py`
- Warns if `container.sif` is missing

**Live mode** (requires `container.sif`):
- Combines all 4 test JSONs into a single list
- Calls `preprocess.py` and checks that output files are created
- Runs full pipeline on `5sbj-assembly1.json` via `apptainer exec` (HelixFold3 uses `8e3r-assembly1.json` with reduced validation settings `HF3_SEEDS=42`, `HF3_DIFF_BATCH_SIZE=1`, `HF3_INFER_TIMES=1` to keep live smoke testing tractable)
- Verifies `prediction_reference.csv` is produced in `evaluation_dir`

HelixFold3 is validated through the same generic `test_algorithm.sh` flow as other algorithms.

```bash
# Examples
./algorithms/test_algorithm.sh --algorithm alphafold3 --dry-run
./algorithms/test_algorithm.sh --algorithm boltz2 --gpu-id 0
./algorithms/test_algorithm.sh --algorithm Protenix --gpu-id 0
```

---

## 15. Acceptance Criteria Per Algorithm

Each algorithm must satisfy all of the following before moving to the next:

- [ ] All 4 test JSONs (`5sbj`, `7fwl`, `8e3r`, `8tuz`) produce correctly
      formatted preprocessed input files in `outputs/input/{algo}/`
- [ ] Model runs without error for each of the 5 seeds, producing 5 samples
      per seed (25 CIF files total per target)
- [ ] `prediction_reference.csv` has **25 rows** (5 seeds × 5 samples) with
      all required columns: `pdb_id`, `seed`, `sample`, `ranking_score`,
      `prediction_path`
- [ ] CIF files are normalized (occupancy = 1, B_iso = 0, entity category
      rebuilt)
- [ ] `prediction_reference.csv` is written to
      `outputs/evaluation/{algorithm}/prediction_reference.csv`
- [ ] No errors on all 4 test JSONs (do not move to the next algorithm until
      all 4 pass)

---

## 16. Quick-Reference: File Paths

| Item | Path |
|------|------|
| Repo root | `/projects/u5fx/hussian-simulation-hdx/projects/FoldBench` |
| Algorithm dirs | `algorithms/{alphafold3,boltz2,openfold3,Protenix,helixfold3}/` |
| Test JSONs | `examples/job_jsons/{5sbj,7fwl,8e3r,8tuz}-assembly1.json` |
| Combined input JSON | `examples/alphafold3_inputs.json` |
| Outputs root | `examples/outputs/` |
| Slurm build scripts | `/projects/u5fx/hussian-simulation-hdx/_submission/_install/FoldBench/` |
| AF3 model weights | `/projects/u5fx/hussian-simulation-hdx/projects/ATLAS_MSA/AF3_weights` |
| Validation script | `algorithms/test_algorithm.sh` |
| HelixFold3 source | `algorithms/helixfold3/PaddleHelix/apps/protein_folding/helixfold3/` |
