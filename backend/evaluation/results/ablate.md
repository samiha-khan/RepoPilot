
### click (synthetic)

| variant | MRR | ΔMRR vs current [95% CI] |
|---|---|---|
| current | 0.490 | |
| previous ranker | 0.318 | -0.173 [-0.223, -0.123] |
| no stemming | 0.435 | -0.055 [-0.094, -0.019] |
| keep query stopwords | 0.385 | -0.105 [-0.134, -0.078] |
| no identifier splitting | 0.254 | -0.236 [-0.295, -0.183] |
| no exact-name priority | 0.490 | +0.000 [+0.000, +0.000] |
| class indexed by full source | 0.507 | +0.016 [-0.007, +0.039] |
| per-field saturation (linear) | 0.447 | -0.043 [-0.079, -0.005] |
| equal field weights | 0.449 | -0.042 [-0.080, -0.004] |

### httpx (synthetic)

| variant | MRR | ΔMRR vs current [95% CI] |
|---|---|---|
| current | 0.450 | |
| previous ranker | 0.363 | -0.087 [-0.148, -0.028] |
| no stemming | 0.441 | -0.009 [-0.062, +0.040] |
| keep query stopwords | 0.348 | -0.101 [-0.142, -0.063] |
| no identifier splitting | 0.300 | -0.150 [-0.223, -0.083] |
| no exact-name priority | 0.450 | +0.000 [+0.000, +0.000] |
| class indexed by full source | 0.400 | -0.050 [-0.077, -0.027] |
| per-field saturation (linear) | 0.433 | -0.016 [-0.065, +0.034] |
| equal field weights | 0.312 | -0.137 [-0.191, -0.089] |

### requests (synthetic)

| variant | MRR | ΔMRR vs current [95% CI] |
|---|---|---|
| current | 0.622 | |
| previous ranker | 0.529 | -0.093 [-0.161, -0.030] |
| no stemming | 0.593 | -0.029 [-0.082, +0.022] |
| keep query stopwords | 0.575 | -0.047 [-0.080, -0.014] |
| no identifier splitting | 0.408 | -0.214 [-0.298, -0.132] |
| no exact-name priority | 0.622 | +0.000 [+0.000, +0.000] |
| class indexed by full source | 0.613 | -0.009 [-0.026, +0.007] |
| per-field saturation (linear) | 0.607 | -0.015 [-0.050, +0.019] |
| equal field weights | 0.538 | -0.084 [-0.129, -0.040] |

### flask (synthetic)

| variant | MRR | ΔMRR vs current [95% CI] |
|---|---|---|
| current | 0.548 | |
| previous ranker | 0.420 | -0.128 [-0.185, -0.078] |
| no stemming | 0.502 | -0.046 [-0.086, -0.006] |
| keep query stopwords | 0.432 | -0.116 [-0.155, -0.082] |
| no identifier splitting | 0.224 | -0.324 [-0.386, -0.259] |
| no exact-name priority | 0.548 | +0.000 [+0.000, +0.000] |
| class indexed by full source | 0.523 | -0.025 [-0.044, -0.007] |
| per-field saturation (linear) | 0.510 | -0.038 [-0.078, -0.001] |
| equal field weights | 0.447 | -0.101 [-0.142, -0.059] |

### click (identifier lookup)

| variant | MRR | ΔMRR vs current [95% CI] |
|---|---|---|
| current | 1.000 | |
| previous ranker | 1.000 | +0.000 [+0.000, +0.000] |
| no stemming | 1.000 | +0.000 [+0.000, +0.000] |
| keep query stopwords | 1.000 | +0.000 [+0.000, +0.000] |
| no identifier splitting | 0.998 | -0.002 [-0.006, +0.000] |
| no exact-name priority | 0.951 | -0.049 [-0.068, -0.031] |
| class indexed by full source | 1.000 | +0.000 [+0.000, +0.000] |
| per-field saturation (linear) | 1.000 | +0.000 [+0.000, +0.000] |
| equal field weights | 1.000 | +0.000 [+0.000, +0.000] |

### httpx (identifier lookup)

| variant | MRR | ΔMRR vs current [95% CI] |
|---|---|---|
| current | 1.000 | |
| previous ranker | 1.000 | +0.000 [+0.000, +0.000] |
| no stemming | 1.000 | +0.000 [+0.000, +0.000] |
| keep query stopwords | 1.000 | +0.000 [+0.000, +0.000] |
| no identifier splitting | 1.000 | +0.000 [+0.000, +0.000] |
| no exact-name priority | 0.982 | -0.018 [-0.033, -0.005] |
| class indexed by full source | 1.000 | +0.000 [+0.000, +0.000] |
| per-field saturation (linear) | 1.000 | +0.000 [+0.000, +0.000] |
| equal field weights | 1.000 | +0.000 [+0.000, +0.000] |

### requests (identifier lookup)

| variant | MRR | ΔMRR vs current [95% CI] |
|---|---|---|
| current | 1.000 | |
| previous ranker | 1.000 | +0.000 [+0.000, +0.000] |
| no stemming | 1.000 | +0.000 [+0.000, +0.000] |
| keep query stopwords | 1.000 | +0.000 [+0.000, +0.000] |
| no identifier splitting | 1.000 | +0.000 [+0.000, +0.000] |
| no exact-name priority | 0.942 | -0.058 [-0.088, -0.034] |
| class indexed by full source | 1.000 | +0.000 [+0.000, +0.000] |
| per-field saturation (linear) | 1.000 | +0.000 [+0.000, +0.000] |
| equal field weights | 1.000 | +0.000 [+0.000, +0.000] |

### flask (identifier lookup)

| variant | MRR | ΔMRR vs current [95% CI] |
|---|---|---|
| current | 1.000 | |
| previous ranker | 1.000 | +0.000 [+0.000, +0.000] |
| no stemming | 1.000 | +0.000 [+0.000, +0.000] |
| keep query stopwords | 1.000 | +0.000 [+0.000, +0.000] |
| no identifier splitting | 1.000 | +0.000 [+0.000, +0.000] |
| no exact-name priority | 0.900 | -0.100 [-0.132, -0.071] |
| class indexed by full source | 1.000 | +0.000 [+0.000, +0.000] |
| per-field saturation (linear) | 1.000 | +0.000 [+0.000, +0.000] |
| equal field weights | 1.000 | +0.000 [+0.000, +0.000] |

### repopilot (identifier lookup)

| variant | MRR | ΔMRR vs current [95% CI] |
|---|---|---|
| current | 1.000 | |
| previous ranker | 1.000 | +0.000 [+0.000, +0.000] |
| no stemming | 1.000 | +0.000 [+0.000, +0.000] |
| keep query stopwords | 1.000 | +0.000 [+0.000, +0.000] |
| no identifier splitting | 1.000 | +0.000 [+0.000, +0.000] |
| no exact-name priority | 0.966 | -0.034 [-0.072, -0.008] |
| class indexed by full source | 1.000 | +0.000 [+0.000, +0.000] |
| per-field saturation (linear) | 1.000 | +0.000 [+0.000, +0.000] |
| equal field weights | 1.000 | +0.000 [+0.000, +0.000] |

### requests (hand-labelled)

| variant | MRR | ΔMRR vs current [95% CI] |
|---|---|---|
| current | 0.907 | |
| previous ranker | 0.729 | -0.178 [-0.329, -0.056] |
| no stemming | 0.880 | -0.028 [-0.083, +0.000] |
| keep query stopwords | 0.907 | +0.000 [+0.000, +0.000] |
| no identifier splitting | 0.708 | -0.199 [-0.375, -0.046] |
| no exact-name priority | 0.907 | +0.000 [+0.000, +0.000] |
| class indexed by full source | 0.907 | +0.000 [+0.000, +0.000] |
| per-field saturation (linear) | 0.843 | -0.065 [-0.185, +0.019] |
| equal field weights | 0.866 | -0.042 [-0.153, +0.056] |

### repopilot (hand-labelled)

| variant | MRR | ΔMRR vs current [95% CI] |
|---|---|---|
| current | 0.917 | |
| previous ranker | 0.917 | +0.000 [-0.083, +0.083] |
| no stemming | 0.889 | -0.028 [-0.083, +0.000] |
| keep query stopwords | 0.944 | +0.028 [+0.000, +0.083] |
| no identifier splitting | 0.537 | -0.380 [-0.602, -0.167] |
| no exact-name priority | 0.917 | +0.000 [+0.000, +0.000] |
| class indexed by full source | 0.944 | +0.028 [+0.000, +0.083] |
| per-field saturation (linear) | 0.889 | -0.028 [-0.083, +0.000] |
| equal field weights | 0.880 | -0.037 [-0.139, +0.056] |
