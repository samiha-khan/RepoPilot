dev corpora: click, httpx | mean MRR; feedback off = 0.4699

| rank | docs | terms | weight | dev MRR |
|---|---|---|---|---|
| 1 | 5 | 5 | 0.1 | 0.4588 |
| 2 | 10 | 10 | 0.1 | 0.4568 |
| 3 | 10 | 5 | 0.1 | 0.4550 |
| 4 | 3 | 5 | 0.1 | 0.4516 |
| 5 | 10 | 20 | 0.1 | 0.4509 |
| 6 | 5 | 10 | 0.1 | 0.4476 |
| 7 | 3 | 10 | 0.1 | 0.4409 |
| 8 | 5 | 20 | 0.1 | 0.4407 |

worst grid point: (10, 20, 0.5) at 0.3177

best dev setting (5, 5, 0.1) against feedback off, every corpus:

| workload | MRR off | MRR on | difference [95% CI] |
|---|---|---|---|
| click docstring [dev] | 0.490 | 0.482 | -0.008 [-0.024, +0.007] |
| click identifier [dev] | 1.000 | 1.000 | +0.000 [+0.000, +0.000] |
| httpx docstring [dev] | 0.450 | 0.436 | -0.014 [-0.036, +0.005] |
| httpx identifier [dev] | 1.000 | 1.000 | +0.000 [+0.000, +0.000] |
| requests docstring [test] | 0.622 | 0.608 | -0.014 [-0.039, +0.011] |
| requests identifier [test] | 1.000 | 1.000 | +0.000 [+0.000, +0.000] |
| flask docstring [test] | 0.548 | 0.529 | -0.019 [-0.039, -0.000] |
| flask identifier [test] | 1.000 | 1.000 | +0.000 [+0.000, +0.000] |
| repopilot identifier [test] | 1.000 | 1.000 | +0.000 [+0.000, +0.000] |
| requests hand-labelled [test] | 0.907 | 0.852 | -0.056 [-0.167, +0.056] |
| repopilot hand-labelled [test] | 0.917 | 0.875 | -0.042 [-0.139, +0.056] |
