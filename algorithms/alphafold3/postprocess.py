"""
postprocess for AlphaFold3.
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
        # Collect pdb_ids from individual input JSON files
        input_json_files = sorted(glob.glob(os.path.join(input_dir, "*.json")))
        pdb_ids = []
        for json_path in input_json_files:
            with open(json_path, "r") as f:
                entry = json.load(f)
            pdb_ids.append(entry["name"])

        # Build list of CIF files to process using ranking_scores.csv
        cif_paths = []
        for pdb_id in pdb_ids:
            ranking_csv = os.path.join(
                prediction_dir, pdb_id, f"{pdb_id}_ranking_scores.csv"
            )
            if not os.path.exists(ranking_csv):
                print(f"Warning: ranking scores not found for {pdb_id}, skipping.")
                continue

            ranking_df = pd.read_csv(ranking_csv)
            for _, row in ranking_df.iterrows():
                seed = str(int(row["seed"]))
                sample = int(row["sample"])
                cif_path = os.path.join(
                    prediction_dir,
                    pdb_id,
                    f"seed-{seed}_sample-{sample}",
                    f"{pdb_id}_seed-{seed}_sample-{sample}_model.cif",
                )
                cif_new_path = os.path.join(
                    os.path.dirname(cif_path),
                    f"{os.path.splitext(os.path.basename(cif_path))[0]}_postprocessed.cif",
                )
                cif_paths.append((pdb_id, cif_path, cif_new_path, seed, sample))

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

        # Re-read ranking scores to build the final reference table
        ranking_cache = {}
        data = []
        for result in results:
            if result is None:
                continue
            pdb_id, new_file_path, seed, sample = result

            # Load ranking_scores.csv once per pdb_id
            if pdb_id not in ranking_cache:
                ranking_csv = os.path.join(
                    prediction_dir, pdb_id, f"{pdb_id}_ranking_scores.csv"
                )
                ranking_cache[pdb_id] = pd.read_csv(ranking_csv)

            df = ranking_cache[pdb_id]
            row = df[(df["seed"].astype(float).astype(int).astype(str) == seed) & (df["sample"] == int(sample))]
            ranking_score = float(row["ranking_score"].values[0]) if len(row) > 0 else 0.0

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
    "--input_dir", required=True, help="Directory containing per-target input JSON files."
)
parser.add_argument(
    "--prediction_dir", required=True, help="Directory containing AlphaFold3 predictions."
)
parser.add_argument(
    "--evaluation_dir", required=True, help="Directory to write prediction_reference.csv."
)
args = parser.parse_args()

postprocess = PostProcess()
postprocess.postprocess(args.input_dir, args.prediction_dir, args.evaluation_dir)
