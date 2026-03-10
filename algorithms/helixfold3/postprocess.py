"""
postprocess for HelixFold3.
1. Normalizes CIF outputs (occupancy=1, B_iso=0, entity category).
2. Generates prediction_reference.csv in evaluation_dir with columns:
   pdb_id, seed, sample, ranking_score, prediction_path.
"""

import argparse
import glob
import json
import multiprocessing as mp
import os
import re

import biotite.structure.io.pdbx as pdbx
import pandas as pd
from tqdm import tqdm


class PostProcess():
    def __init__(self):
        super().__init__()

    def process_file(self, item):
        pdb_id, seed, sample, cif_path, score_path, new_cif_path = item
        if not os.path.exists(cif_path):
            return None

        dict_entity_id = {}

        cif_file = pdbx.CIFFile.read(cif_path)
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
            else:
                if dict_entity_id[entity_id][1] != group_pdb:
                    dict_entity_id[entity_id] = ("polymer", group_pdb)

        block["entity"] = pdbx.CIFCategory(
            {
                "id": list(dict_entity_id.keys()),
                "type": [dict_entity_id[k][0] for k in dict_entity_id.keys()],
            }
        )
        cif_file.write(new_cif_path)

        ranking_score = 0.0
        if os.path.exists(score_path):
            with open(score_path, "r") as f:
                score_json = json.load(f)
            ranking_score = float(score_json.get("ranking_confidence", 0.0))

        return {
            "pdb_id": pdb_id,
            "seed": seed,
            "sample": sample,
            "ranking_score": ranking_score,
            "prediction_path": new_cif_path,
        }

    @staticmethod
    def _sort_pred_dirs(pred_dirs, pdb_id):
        pattern = re.compile(rf"^{re.escape(pdb_id)}-pred-(\d+)-(\d+)$")

        def _key(path):
            name = os.path.basename(path)
            match = pattern.match(name)
            if match:
                return int(match.group(1)), int(match.group(2))
            return 9999, 9999

        return sorted(pred_dirs, key=_key)

    def postprocess(self, input_dir, prediction_dir, evaluation_dir):
        os.makedirs(evaluation_dir, exist_ok=True)

        input_json_files = sorted(glob.glob(os.path.join(input_dir, "*.json")))
        pdb_ids = [os.path.splitext(os.path.basename(path))[0] for path in input_json_files]

        work_items = []
        for pdb_id in pdb_ids:
            seed_dirs = sorted(glob.glob(os.path.join(prediction_dir, pdb_id, "seed_*")))
            for seed_dir in seed_dirs:
                seed = os.path.basename(seed_dir).replace("seed_", "")
                pred_root = os.path.join(seed_dir, pdb_id)
                pred_dirs = glob.glob(os.path.join(pred_root, f"{pdb_id}-pred-*-*"))
                pred_dirs = self._sort_pred_dirs(pred_dirs, pdb_id)[:5]

                for sample, pred_dir in enumerate(pred_dirs):
                    cif_path = os.path.join(pred_dir, "predicted_structure.cif")
                    score_path = os.path.join(pred_dir, "all_results.json")
                    new_cif_path = os.path.join(
                        pred_dir, f"{pdb_id}_seed_{seed}_sample_{sample}_postprocessed.cif"
                    )
                    work_items.append((pdb_id, seed, sample, cif_path, score_path, new_cif_path))

        print(f"Processing {len(work_items)} CIF files")

        if len(work_items) == 0:
            out_csv = os.path.join(evaluation_dir, "prediction_reference.csv")
            pd.DataFrame(
                columns=["pdb_id", "seed", "sample", "ranking_score", "prediction_path"]
            ).to_csv(out_csv, index=False)
            print(f"prediction_reference.csv written to {out_csv} (0 rows)")
            return

        num_cores = mp.cpu_count()
        num_processes = max(1, int(num_cores * 0.8))
        print(f"Will use {num_processes} processes for parallel processing")

        with mp.Pool(processes=num_processes) as pool:
            results = list(
                tqdm(
                    pool.imap(self.process_file, work_items),
                    total=len(work_items),
                    desc="Processing progress",
                )
            )

        rows = [r for r in results if r is not None]
        out_csv = os.path.join(evaluation_dir, "prediction_reference.csv")
        pd.DataFrame(rows).to_csv(out_csv, index=False)
        print(f"prediction_reference.csv written to {out_csv} ({len(rows)} rows)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input_dir",
        required=True,
        help="Directory containing per-target HelixFold3 input JSON files.",
    )
    parser.add_argument(
        "--prediction_dir",
        required=True,
        help="Directory containing HelixFold3 prediction outputs.",
    )
    parser.add_argument(
        "--evaluation_dir",
        required=True,
        help="Directory to write prediction_reference.csv.",
    )
    args = parser.parse_args()

    postprocess = PostProcess()
    postprocess.postprocess(args.input_dir, args.prediction_dir, args.evaluation_dir)
