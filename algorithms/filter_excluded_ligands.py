"""
Standalone script to filter excluded CCD ligands from AF3 input JSON files.

Removes any ligand sequence entries whose ccdCodes[0] is in the exclusion set
(crystallization aids + common buffer/artifact molecules from HelixFold3).

Usage:
    python algorithms/filter_excluded_ligands.py \
        --input  path/to/af3_input.json \
        --output path/to/af3_input_filtered.json

If --output is omitted, the input file is overwritten in-place.
"""

import argparse
import json

_CRYSTALLIZATION_AIDS = {
    "SO4", "GOL", "EDO", "PO4", "ACT", "PEG", "DMS", "TRS",
    "PGE", "PG4", "FMT", "EPE", "MPD", "MES", "CD", "IOD",
}

_LIGAND_EXCLUSION_LIST = {
    "144", "15P", "1PE", "2F2", "2JC", "3HR", "3SY", "7N5", "7PE", "9JE",
    "AAE", "ABA", "ACE", "ACN", "ACT", "ACY", "AZI", "BAM", "BCN", "BCT",
    "BDN", "BEN", "BME", "BO3", "BTB", "BTC", "BU1", "C8E", "CAD", "CAQ",
    "CBM", "CCN", "CIT", "CLR", "CM", "CMO", "CO3", "CPT", "CXS", "D10",
    "DEP", "DIO", "DMS", "DN", "DOD", "DOX", "EDO", "EEE", "EGL", "EOH",
    "EOX", "EPE", "ETF", "FCY", "FJO", "FLC", "FMT", "FW5", "GOL", "GSH",
    "GTT", "GYF", "HED", "IHP", "IHS", "IMD", "IOD", "IPA", "IPH", "LDA",
    "MB3", "MEG", "MES", "MLA", "MLI", "MOH", "MPD", "MRD", "MSE", "MYR",
    "N", "NH2", "NH4", "NHE", "NO3", "O4B", "OHE", "OLA", "OLC", "OMB",
    "OME", "OXA", "P6G", "PE3", "PE4", "PEG", "PEO", "PEP", "PG0", "PG4",
    "PGE", "PGR", "PLM", "PO4", "POL", "POP", "PVO", "SAR", "SCN", "SEO",
    "SEP", "SIN", "SO4", "SPD", "SPM", "STE", "STO", "STU", "TAR", "TBU",
    "TME", "TPO", "TRS", "UNK", "UNL", "UNX", "UPL", "URE",
}

EXCLUDE_CCD = _CRYSTALLIZATION_AIDS | _LIGAND_EXCLUSION_LIST


def filter_excluded_ligands(entries):
    """Filter excluded CCD ligands from a list of AF3 input entries."""
    for entry in entries:
        before = len(entry.get("sequences", []))
        entry["sequences"] = [
            seq for seq in entry.get("sequences", [])
            if not (
                "ligand" in seq
                and any(c in EXCLUDE_CCD for c in seq["ligand"].get("ccdCodes", []))
            )
        ]
        removed = before - len(entry["sequences"])
        if removed:
            print(f"  [{entry.get('name', '?')}] Removed {removed} excluded CCD ligand(s).")
    return entries


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Filter excluded CCD ligands from AF3 input JSON.")
    parser.add_argument("--input", required=True, help="Path to AF3 input JSON.")
    parser.add_argument("--output", help="Output path (default: overwrite input in-place).")
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)

    data = filter_excluded_ligands(data)

    out_path = args.output if args.output else args.input
    with open(out_path, "w") as f:
        json.dump(data, f, indent=4)
    print(f"Filtered JSON written to {out_path}")
