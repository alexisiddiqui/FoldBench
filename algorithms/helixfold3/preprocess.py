"""
preprocess for HelixFold3.
Convert AF3 input JSON list to per-target HelixFold3 native JSON files.
"""

import argparse
import json
import os
import sys

# Import shared CCD exclusion set (algorithms/ is mounted at /algo/ inside container)
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
    from filter_excluded_ligands import EXCLUDE_CCD as _HF3_EXCLUDE_CCD
except Exception:
    # Fallback: hardcoded crystallization aids list
    _HF3_EXCLUDE_CCD = {
        "SO4", "GOL", "EDO", "PO4", "ACT", "PEG", "DMS", "TRS",
        "PGE", "PG4", "FMT", "EPE", "MPD", "MES", "CD", "IOD",
    }


class PreProcess():
    def __init__(self):
        super().__init__()

    @staticmethod
    def _count_from_id(chain_id):
        if isinstance(chain_id, list):
            return len(chain_id)
        return 1

    @staticmethod
    def _convert_modifications(seq_type, modifications):
        if seq_type == "protein":
            pos_key = "ptmPosition"
            type_key = "ptmType"
        else:
            pos_key = "basePosition"
            type_key = "modificationType"

        converted = []
        for mod in modifications:
            if pos_key in mod and type_key in mod:
                converted.append(
                    {
                        "type": "residue_replace",
                        "index": int(mod[pos_key]),
                        "ccd": str(mod[type_key]),
                    }
                )
        return converted

    def format_single_input(self, input_data, input_dir, target_name):
        entities = []

        for seq_idx, seq in enumerate(input_data.get("sequences", [])):
            seq_type = next(iter(seq))
            seq_content = seq[seq_type]

            if seq_type in ("protein", "rna", "dna"):
                entity = {
                    "type": seq_type,
                    "sequence": seq_content.get("sequence", ""),
                    "count": self._count_from_id(seq_content.get("id")),
                }

                # Extract chain ID for MSA file naming
                chain_id = seq_content.get("id")
                if isinstance(chain_id, list):
                    chain_id = chain_id[0] if chain_id else f"chain_{seq_idx}"

                # Extract and write MSA from AF3 JSON
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
                    entity["msa"] = msa_path

                modifications = self._convert_modifications(
                    seq_type, seq_content.get("modifications", [])
                )
                if modifications:
                    entity["modification"] = modifications
                entities.append(entity)
            elif seq_type == "ligand":
                ccd_codes = seq_content.get("ccdCodes", [])
                if not ccd_codes:
                    continue
                ccd = str(ccd_codes[0])
                if ccd in _HF3_EXCLUDE_CCD:
                    continue  # skip unsupported/excluded CCD
                entities.append(
                    {
                        "type": "ligand",
                        "ccd": ccd,
                        "count": self._count_from_id(seq_content.get("id")),
                    }
                )

        return {"entities": entities}

    def preprocess(self, af3_input_json_path, input_dir):
        with open(af3_input_json_path, "r") as f:
            folding_inputs = json.load(f)
        if isinstance(folding_inputs, dict):
            folding_inputs = [folding_inputs]

        os.makedirs(input_dir, exist_ok=True)

        for entry in folding_inputs:
            pdb_id = entry["name"]
            mapped = self.format_single_input(entry, input_dir, pdb_id)
            output_path = os.path.join(input_dir, f"{pdb_id}.json")
            with open(output_path, "w") as f:
                json.dump(mapped, f, indent=4)

        print(f"{len(folding_inputs)} folding inputs written to {input_dir}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--af3_input_json",
        required=True,
        help="The path to the combined AF3 input .json file.",
    )
    parser.add_argument(
        "--input_dir",
        required=True,
        help="The path to write per-target HelixFold3 input JSON files.",
    )
    args = parser.parse_args()

    preprocess = PreProcess()
    preprocess.preprocess(args.af3_input_json, args.input_dir)
