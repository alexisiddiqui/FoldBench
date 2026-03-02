"""
postprocess for OpenFold3.
1. Normalizes CIF outputs (occupancy=1, B_iso=0, entity category).
2. Generates prediction_reference.csv in evaluation_dir with columns:
   pdb_id, seed, sample, ranking_score, prediction_path.
"""

import argparse
import os
import json
import multiprocessing as mp

import pandas as pd
from tqdm import tqdm
import biotite.structure.io.pdbx as pdbx


class PostProcess():
    def __init__(self):
        pass

    def process_file(self, cif_paths):
        """Process a single CIF file: normalize occupancy, B_iso, and entity category.

        Args:
            cif_paths: tuple of (pdb_id, file_path, new_file_path, seed, sample)

        Returns:
            tuple: (pdb_id, new_file_path, seed, sample) if successful, None otherwise
        """
        pdb_id, file_path, new_file_path, seed, sample = cif_paths

        if not os.path.exists(file_path):
            return None

        dict_entity_id = {}

        cif_file = pdbx.CIFFile.read(file_path)
        block = cif_file.block
        atom_site = block.get("atom_site")

        # Set occupancy to 1 and B_iso_or_equiv to 0
        atom_site["occupancy"] = pdbx.CIFColumn(
            pdbx.CIFData(["1" for _ in range(len(atom_site["group_PDB"]))])
        )
        atom_site["B_iso_or_equiv"] = pdbx.CIFColumn(
            pdbx.CIFData(["0" for _ in range(len(atom_site["group_PDB"]))])
        )

        # Rebuild entity category
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
        """Postprocess predictions: normalize CIFs and generate prediction_reference.csv.

        Args:
            input_dir: path to the algorithm input directory (contains inputs.json)
            prediction_dir: path to the algorithm predictions directory
            evaluation_dir: path to the evaluation directory (where CSV will be written)
        """
        # Read pdb_ids from inputs.json queries dict
        with open(os.path.join(input_dir, "inputs.json")) as f:
            inputs_data = json.load(f)
            pdb_ids = list(inputs_data["queries"].keys())

        # OpenFold3 uses these exact seeds
        seeds = ["42", "66", "101", "2024", "8888"]
        # OF3 uses 1-indexed sample numbers in filenames (1, 2, 3, 4, 5)
        samples_1indexed = [1, 2, 3, 4, 5]

        cif_paths = []

        # Collect all CIF files to process
        for pdb_id in pdb_ids:
            for seed in seeds:
                for s in samples_1indexed:
                    cif = os.path.join(
                        prediction_dir,
                        pdb_id,
                        f"seed_{seed}",
                        f"{pdb_id}_seed_{seed}_sample_{s}_model.cif"
                    )
                    if os.path.exists(cif):
                        new_path = cif.replace("_model.cif", "_model_postprocessed.cif")
                        # Store 0-indexed sample for CSV (s - 1)
                        cif_paths.append((pdb_id, cif, new_path, seed, s - 1))

        print(f"Processing {len(cif_paths)} CIF files")
        num_cores = mp.cpu_count()
        num_processes = max(1, int(num_cores * 0.8))
        print(f"Will use {num_processes} processes for parallel processing")

        # Process CIF files in parallel
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
            # Sample in filename is 1-indexed (sample + 1), so we need to convert
            s_1indexed = sample + 1
            confidence_path = os.path.join(
                prediction_dir,
                pdb_id,
                f"seed_{seed}",
                f"{pdb_id}_seed_{seed}_sample_{s_1indexed}_confidences_aggregated.json"
            )

            ranking_score = 0.0
            if os.path.exists(confidence_path):
                try:
                    with open(confidence_path) as f:
                        confidence = json.load(f)
                    # Prefer sample_ranking_score (requires pae_enabled preset)
                    # Fall back to avg_plddt if not available
                    ranking_score = confidence.get(
                        "sample_ranking_score",
                        confidence.get("avg_plddt", 0.0)
                    )
                except Exception as e:
                    print(f"Warning: could not read confidence from {confidence_path}: {e}")

            data.append({
                "pdb_id": pdb_id,
                "seed": seed,
                "sample": sample,
                "ranking_score": ranking_score,
                "prediction_path": new_file_path
            })

        # Write prediction reference CSV
        df = pd.DataFrame(data)
        csv_path = os.path.join(evaluation_dir, "prediction_reference.csv")
        os.makedirs(evaluation_dir, exist_ok=True)
        df.to_csv(csv_path, index=False)
        print(f"Prediction reference written to {csv_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input_dir",
        required=True,
        help="The path to the algorithm input directory."
    )
    parser.add_argument(
        "--prediction_dir",
        required=True,
        help="The path to the algorithm predictions directory."
    )
    parser.add_argument(
        "--evaluation_dir",
        required=True,
        help="The evaluation directory where prediction_reference.csv will be written."
    )
    args = parser.parse_args()

    postprocess = PostProcess()
    postprocess.postprocess(args.input_dir, args.prediction_dir, args.evaluation_dir)
