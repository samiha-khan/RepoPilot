
### repopilot (backend/app): 90 chunks

| ranker | queries | R@1 | R@5 | R@10 | MRR [95% CI] | nDCG@10 |
|---|---|---|---|---|---|---|
| previous ranker | 18 | 0.833 | 1.000 | 1.000 | 0.917 [0.806, 1.000] | 0.938 |
| BM25F (current) | 18 | 0.833 | 1.000 | 1.000 | 0.917 [0.833, 1.000] | 0.938 |

### psf/requests (src/requests): 283 chunks

| ranker | queries | R@1 | R@5 | R@10 | MRR [95% CI] | nDCG@10 |
|---|---|---|---|---|---|---|
| previous ranker | 18 | 0.556 | 0.944 | 1.000 | 0.729 [0.576, 0.868] | 0.797 |
| BM25F (current) | 18 | 0.833 | 1.000 | 1.000 | 0.907 [0.796, 1.000] | 0.931 |
