"""
preprocess for AlphaFold3.
AF3 natively reads its own JSON format, so preprocessing just splits the
combined alphafold3_inputs.json list into individual per-target JSON files.
"""

import argparse
import os
import json


class PreProcess():
    def __init__(self):
        super().__init__()

    def preprocess(self, af3_input_json_path, input_dir):
        """
        af3_input_json_path: path to the combined AF3 input JSON (list of targets)
        input_dir: directory to write one JSON file per target
        """
        with open(af3_input_json_path, "r") as f:
            folding_inputs = json.load(f)

        os.makedirs(input_dir, exist_ok=True)

        for entry in folding_inputs:
            name = entry["name"]
            out_path = os.path.join(input_dir, f"{name}.json")
            with open(out_path, "w") as f:
                json.dump(entry, f, indent=4)

        print(f"{len(folding_inputs)} folding inputs written to {input_dir}.")


parser = argparse.ArgumentParser()
parser.add_argument(
    "--af3_input_json",
    help="The path to the combined AF3 input .json file.",
)
parser.add_argument(
    "--input_dir",
    help="The path to write per-target JSON files for AlphaFold3.",
)
args = parser.parse_args()

preprocess = PreProcess()
preprocess.preprocess(args.af3_input_json, args.input_dir)
