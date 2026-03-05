"""
preprocess for Boltz2.
Convert AF3 input JSON list to individual Boltz YAML files (one per target).
"""

import argparse
import os
import json
import yaml


class PreProcess():
    def __init__(self):
        super().__init__()

    def format_single_input(self, input_data, input_dir, target_name):
        """
        Convert AF3 input data to Boltz YAML format.

        Args:
            input_data: single AF3 input dict
            input_dir: directory to write MSA and template files
            target_name: name of the target (for file naming)

        Returns:
            dict: Boltz YAML structure (ready for yaml.dump)
        """
        boltz_data = {
            "version": 1,
            "sequences": []
        }

        # Process each sequence in the AF3 input
        for seq_idx, seq in enumerate(input_data.get("sequences", [])):
            seq_type = next(iter(seq))  # protein, rna, dna, or ligand
            seq_content = seq[seq_type]

            if seq_type == "protein":
                protein_entry = {
                    "protein": {
                        "id": seq_content.get("id", []),
                        "sequence": seq_content.get("sequence", "")
                    }
                }

                # Extract and write MSA from AF3 JSON
                chain_id = seq_content.get("id")
                if isinstance(chain_id, list):
                    chain_id = chain_id[0] if chain_id else f"chain_{seq_idx}"

                unpaired_msa = seq_content.get("unpairedMsa")
                paired_msa = seq_content.get("pairedMsa", "")

                if unpaired_msa is not None:
                    # Merge unpaired and paired MSAs
                    merged_msa = unpaired_msa
                    if paired_msa:
                        merged_msa += "\n" + paired_msa

                    # Write MSA to disk
                    msa_path = os.path.join(input_dir, f"{target_name}_{chain_id}.a3m")
                    os.makedirs(input_dir, exist_ok=True)
                    with open(msa_path, "w") as f:
                        f.write(merged_msa)
                    protein_entry["protein"]["msa"] = msa_path

                # Add modifications if present
                modifications = []
                for mod in seq_content.get("modifications", []):
                    modifications.append({
                        "position": mod.get("ptmPosition"),
                        "ccd": mod.get("ptmType")
                    })
                if modifications:
                    protein_entry["protein"]["modifications"] = modifications

                boltz_data["sequences"].append(protein_entry)

            elif seq_type == "rna":
                rna_entry = {
                    "rna": {
                        "id": seq_content.get("id", []),
                        "sequence": seq_content.get("sequence", "")
                    }
                }

                # Add modifications if present
                modifications = []
                for mod in seq_content.get("modifications", []):
                    modifications.append({
                        "position": mod.get("basePosition"),
                        "ccd": mod.get("modificationType")
                    })
                if modifications:
                    rna_entry["rna"]["modifications"] = modifications

                boltz_data["sequences"].append(rna_entry)

            elif seq_type == "dna":
                dna_entry = {
                    "dna": {
                        "id": seq_content.get("id", []),
                        "sequence": seq_content.get("sequence", "")
                    }
                }

                # Add modifications if present
                modifications = []
                for mod in seq_content.get("modifications", []):
                    modifications.append({
                        "position": mod.get("basePosition"),
                        "ccd": mod.get("modificationType")
                    })
                if modifications:
                    dna_entry["dna"]["modifications"] = modifications

                boltz_data["sequences"].append(dna_entry)

            elif seq_type == "ligand":
                ligand_entry = {
                    "ligand": {
                        "id": seq_content.get("id", [])
                    }
                }

                # CCD code (take first one if multiple)
                ccd_codes = seq_content.get("ccdCodes", [])
                if ccd_codes:
                    ligand_entry["ligand"]["ccd"] = ccd_codes[0]

                boltz_data["sequences"].append(ligand_entry)

        return boltz_data

    def preprocess(self, af3_input_json_path, input_dir):
        """
        Convert AF3 JSON list to individual Boltz YAML files.

        Args:
            af3_input_json_path: path to combined AF3 input JSON (list of targets)
            input_dir: directory to write one YAML file per target
        """
        with open(af3_input_json_path, "r") as f:
            folding_inputs = json.load(f)

        os.makedirs(input_dir, exist_ok=True)

        for entry in folding_inputs:
            pdb_id = entry["name"]
            boltz_yaml = self.format_single_input(entry, input_dir, pdb_id)

            out_path = os.path.join(input_dir, f"{pdb_id}.yaml")
            with open(out_path, "w") as f:
                yaml.dump(boltz_yaml, f, default_flow_style=False, sort_keys=False)

        print(f"{len(folding_inputs)} folding inputs written to {input_dir}.")


parser = argparse.ArgumentParser()
parser.add_argument(
    "--af3_input_json",
    help="The path to the combined AF3 input .json file.",
)
parser.add_argument(
    "--input_dir",
    help="The path to write per-target YAML files for Boltz2.",
)
args = parser.parse_args()

preprocess = PreProcess()
preprocess.preprocess(args.af3_input_json, args.input_dir)
