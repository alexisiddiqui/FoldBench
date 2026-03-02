
This is the main inference script that runs your model. It will be executed from within the Apptainer environment.

* **Input:** It should read the preprocessed data from `./outputs/input/{algorithm_name}/`.
* **Function:** Execute your model's prediction command-line interface.
* **Output:** The prediction artifacts (e.g., `.cif` or `.pdb` files) must be written to the prediction directory: `./outputs/prediction/{algorithm_name}/`.
