"""
postprocess for Boltz2.
1. Normalizes CIF outputs (occupancy=1, B_iso=0, entity category).
2. Generates prediction_reference.csv in evaluation_dir with columns:
   pdb_id, seed, sample, ranking_score, prediction_path.
"""

import argparse
import os
import json
import glob
import multiprocessing as mp

import pandas as pd
from tqdm import tqdm
import biotite.structure.io.pdbx as pdbx


class PostProcess():
    def __init__(self):
        pass

    def process_file(self, cif_paths):
        pdb_id, file_path, new_file_path, seed, sample = cif_paths

        if not os.path.exists(file_path):
            return None

        dict_entity_id = {}

        cif_file = pdbx.CIFFile.read(file_path)
        block = cif_file.block
        atom_site = block.get("atom_site")

        atom_site["occupancy"] = pdbx.CIFColumn(
            pdbx.CIFData(["1" for _ in range(len(atom_site["group_PDB"]))])
        )
        atom_site["B_iso_or_equiv"] = pdbx.CIFColumn(
            pdbx.CIFData(["0" for _ in range(len(atom_site["group_PDB"]))])
        )

        label_entity_ids = atom_site["label_entity_id"].as_array().tolist()
        group_pdbs = atom_site["group_PDB"].as_array().tolist()
        for entity_id, group_pdb in zip(label_entity_ids, group_pdbs):
            if entity_id not in dict_entity_id:
                if group_pdb == "ATOM":
                    dict_entity_id[entity_id] = ("polymer", group_pdb)
                else:
                    dict_entity_id[entity_id] = ("non-polymer", group_pdb)
            else:  # modification: ATOM+HETATM entity → polymer
                if dict_entity_id[entity_id][1] != group_pdb:
                    dict_entity_id[entity_id] = ("polymer", group_pdb)

        block["entity"] = pdbx.CIFCategory(
            {
                "id": list(dict_entity_id.keys()),
                "type": [dict_entity_id[k][0] for k in dict_entity_id.keys()],
            }
        )

        cif_file.write(new_file_path)

        return pdb_id, new_file_path, seed, sample

    def postprocess(self, input_dir, prediction_dir, evaluation_dir):
        # Collect pdb_ids from individual input YAML files
        input_yaml_files = sorted(glob.glob(os.path.join(input_dir, "*.yaml")))
        pdb_ids = []
        for yaml_path in input_yaml_files:
            # Extract pdb_id from filename (remove .yaml extension)
            pdb_id = os.path.splitext(os.path.basename(yaml_path))[0]
            pdb_ids.append(pdb_id)

        # Find seed subdirectories
        seed_dirs = sorted(glob.glob(os.path.join(prediction_dir, "seed_*")))

        # Build list of CIF files to process
        cif_paths = []
        for seed_dir in seed_dirs:
            seed = os.path.basename(seed_dir).replace("seed_", "")

            # Find boltz_results_* subdirectories (one per yaml with per-file invocations)
            boltz_result_dirs = glob.glob(os.path.join(seed_dir, "boltz_results_*"))
            if not boltz_result_dirs:
                print(f"Warning: no boltz_results_* dir found in {seed_dir}, skipping.")
                continue

            for pdb_id in pdb_ids:
                pred_dir = None
                for brd in boltz_result_dirs:
                    candidate = os.path.join(brd, "predictions", pdb_id)
                    if os.path.exists(candidate):
                        pred_dir = candidate
                        break
                if pred_dir is None:
                    print(f"Warning: {pdb_id} not found in any boltz_results_* dir, skipping.")
                    continue

                # Look for model CIF files (exclude postprocessed from previous runs)
                model_cifs = sorted(
                    f for f in glob.glob(os.path.join(pred_dir, f"{pdb_id}_model_*.cif"))
                    if "_postprocessed" not in os.path.basename(f)
                )
                for cif_file in model_cifs:
                    # Extract sample number from filename (e.g., "model_0" -> 0)
                    basename = os.path.basename(cif_file)
                    sample_str = basename.split("_model_")[1].replace(".cif", "")
                    sample = int(sample_str)

                    cif_new_path = os.path.join(
                        os.path.dirname(cif_file),
                        f"{os.path.splitext(os.path.basename(cif_file))[0]}_postprocessed.cif",
                    )
                    cif_paths.append((pdb_id, cif_file, cif_new_path, seed, sample))

        print(f"Processing {len(cif_paths)} CIF files")
        num_cores = mp.cpu_count()
        num_processes = max(1, int(num_cores * 0.8))
        print(f"Will use {num_processes} processes for parallel processing")

        with mp.Pool(processes=num_processes) as pool:
            results = list(
                tqdm(
                    pool.imap(self.process_file, cif_paths),
                    total=len(cif_paths),
                    desc="Processing progress",
                )
            )

        # Build prediction reference CSV
        data = []
        for result in results:
            if result is None:
                continue
            pdb_id, new_file_path, seed, sample = result

            # Load confidence score from JSON
            # Confidence JSON is in the same directory as the CIF file
            pred_dir = os.path.dirname(new_file_path)
            confidence_json = os.path.join(
                pred_dir, f"confidence_{pdb_id}_model_{sample}.json"
            )

            ranking_score = 0.0
            if os.path.exists(confidence_json):
                try:
                    with open(confidence_json, "r") as f:
                        confidence = json.load(f)
                    ranking_score = float(confidence.get("confidence_score", 0.0))
                except Exception as e:
                    print(f"Warning: could not read confidence score from {confidence_json}: {e}")

            data.append(
                {
                    "pdb_id": pdb_id,
                    "seed": seed,
                    "sample": sample,
                    "ranking_score": ranking_score,
                    "prediction_path": new_file_path,
                }
            )

        os.makedirs(evaluation_dir, exist_ok=True)
        out_csv = os.path.join(evaluation_dir, "prediction_reference.csv")
        pd.DataFrame(data).to_csv(out_csv, index=False)
        print(f"prediction_reference.csv written to {out_csv} ({len(data)} rows)")


parser = argparse.ArgumentParser()
parser.add_argument(
    "--input_dir", required=True, help="Directory containing per-target input YAML files."
)
parser.add_argument(
    "--prediction_dir", required=True, help="Directory containing Boltz2 predictions."
)
parser.add_argument(
    "--evaluation_dir", required=True, help="Directory to write prediction_reference.csv."
)
args = parser.parse_args()

postprocess = PostProcess()
postprocess.postprocess(args.input_dir, args.prediction_dir, args.evaluation_dir)
