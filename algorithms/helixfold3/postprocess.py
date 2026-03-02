### 4. ✨ `postprocess.py`
This script standardizes your model's output for evaluation. It must contain a `PostProcess.postprocess()` method and perform two key tasks:

1.  **Generate Prediction Summary:** Create a summary file named `prediction_reference.csv` in the evaluation directory: `./outputs/evaluation/{algorithm_name}/prediction_reference.csv`. This CSV file is **required** for the benchmark and must include the following columns: `pdb_id`, `seed`, `sample`, `ranking_score`, and `prediction_path`.
2.  **Format for Evaluation:** Convert your model's raw output files (located in `./outputs/prediction/{algorithm_name}/`) into a format compatible with our evaluation tools ([OpenStructure](https://git.scicore.unibas.ch/schwede/openstructure) and [DockQ](https://github.com/bjornwallner/DockQ)).
