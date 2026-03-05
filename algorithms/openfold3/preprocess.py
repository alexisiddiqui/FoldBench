"""
preprocess for OpenFold3.
Convert AF3 input JSON to OpenFold3 native query JSON format.
"""

import argparse
import os
import json
from tqdm import tqdm


class PreProcess():
    def __init__(self):
        super().__init__()

    def format_single_input(self, input_data, input_dir, target_name):
        """Convert one AF3 target dict to an OF3 query dict.

        Args:
            input_data: single AF3 input dict with 'sequences' list
            input_dir: directory to write MSA and template files
            target_name: name of the target (for file naming)

        Returns:
            dict: OF3 query structure with 'chains' list
        """
        chains = []
        for seq_idx, seq in enumerate(input_data["sequences"]):
            seq_type = next(iter(seq))
            content = seq[seq_type]
            chain = {"molecule_type": seq_type}  # protein/rna/dna/ligand

            if seq_type in ("protein", "rna", "dna"):
                # Handle chain IDs (can be string or list)
                chain_ids = content["id"] if isinstance(content["id"], list) else [content["id"]]
                chain["chain_ids"] = chain_ids
                chain["sequence"] = content["sequence"]

                # Extract chain ID for MSA file naming
                chain_id = chain_ids[0] if chain_ids else f"chain_{seq_idx}"

                # Extract and write MSA from AF3 JSON
                unpaired_msa = content.get("unpairedMsa")
                paired_msa = content.get("pairedMsa", "")

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
                    chain["msa_path"] = msa_path

                # Convert modifications to non_canonical_residues
                mods = {}
                pos_key = "ptmPosition" if seq_type == "protein" else "basePosition"
                type_key = "ptmType" if seq_type == "protein" else "modificationType"

                for m in content.get("modifications", []):
                    mods[str(m[pos_key])] = m[type_key]

                if mods:
                    chain["non_canonical_residues"] = mods

            elif seq_type == "ligand":
                # Handle chain IDs
                chain_ids = content["id"] if isinstance(content["id"], list) else [content["id"]]
                chain["chain_ids"] = chain_ids

                # Handle CCD codes (can be single or list)
                ccd = content.get("ccdCodes", [])
                chain["ccd_codes"] = ccd[0] if len(ccd) == 1 else ccd

            chains.append(chain)

        return {"chains": chains}

    def preprocess(self, af3_input_json_path, input_dir):
        """Convert AF3 input JSON to OF3 query JSON.

        Args:
            af3_input_json_path: path to the AF3 input JSON file
            input_dir: path to the input directory for the algorithm
        """
        with open(af3_input_json_path) as f:
            folding_inputs = json.load(f)

        os.makedirs(input_dir, exist_ok=True)
        queries = {}

        for entry in tqdm(folding_inputs):
            queries[entry["name"]] = self.format_single_input(entry, input_dir, entry["name"])

        output = {"queries": queries}
        output_path = os.path.join(input_dir, "inputs.json")
        with open(output_path, "w") as f:
            json.dump(output, f, indent=4)

        print(f"{len(queries)} queries written to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--af3_input_json",
        help="The path to the input .json file.",
        required=True
    )
    parser.add_argument(
        "--input_dir",
        help="The path to write prepared input data in the format expected by the algorithm.",
        required=True
    )
    args = parser.parse_args()

    preprocess = PreProcess()
    preprocess.preprocess(args.af3_input_json, args.input_dir)
