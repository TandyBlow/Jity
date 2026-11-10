# HPC run records

Only small JSON evidence is kept here: `report.json` (training identity, losses,
samples) and `grade.json` (beat grading). Weights, checkpoints, `.pt` files and
raw job logs stay on the cluster or in the local model cache and are never
committed. Each `report.json` names its base, data hash, seed, template and job
id so the run can be reproduced.
