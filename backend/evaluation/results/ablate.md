
### click (synthetic)

| variant | MRR | ΔMRR vs current [95% CI] |
|---|---|---|
| current | 0.492 | |
| previous ranker | 0.315 | -0.178 [-0.229, -0.127] |
| no stemming | 0.430 | -0.062 [-0.103, -0.024] |
| keep query stopwords | 0.385 | -0.108 [-0.139, -0.080] |
| no identifier splitting | 0.253 | -0.240 [-0.300, -0.185] |
| no exact-name priority | 0.492 | +0.000 [+0.000, +0.000] |
| class indexed by full source | 0.500 | +0.008 [-0.014, +0.031] |
| per-field saturation (linear) | 0.434 | -0.058 [-0.094, -0.020] |
| equal field weights | 0.450 | -0.042 [-0.083, -0.003] |

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
| current | 0.633 | |
| previous ranker | 0.524 | -0.109 [-0.175, -0.045] |
| no stemming | 0.595 | -0.038 [-0.090, +0.012] |
| keep query stopwords | 0.584 | -0.049 [-0.084, -0.015] |
| no identifier splitting | 0.401 | -0.232 [-0.313, -0.151] |
| no exact-name priority | 0.633 | +0.000 [+0.000, +0.000] |
| class indexed by full source | 0.613 | -0.020 [-0.037, -0.005] |
| per-field saturation (linear) | 0.604 | -0.029 [-0.063, +0.004] |
| equal field weights | 0.549 | -0.084 [-0.131, -0.041] |

### flask (synthetic)

| variant | MRR | ΔMRR vs current [95% CI] |
|---|---|---|
| current | 0.542 | |
| previous ranker | 0.420 | -0.122 [-0.177, -0.071] |
| no stemming | 0.505 | -0.038 [-0.076, +0.001] |
| keep query stopwords | 0.428 | -0.114 [-0.150, -0.079] |
| no identifier splitting | 0.224 | -0.318 [-0.380, -0.255] |
| no exact-name priority | 0.542 | +0.000 [+0.000, +0.000] |
| class indexed by full source | 0.527 | -0.015 [-0.035, +0.004] |
| per-field saturation (linear) | 0.506 | -0.036 [-0.077, +0.002] |
| equal field weights | 0.445 | -0.097 [-0.137, -0.058] |

### click (identifier lookup)

| variant | MRR | ΔMRR vs current [95% CI] |
|---|---|---|
| current | 1.000 | |
| previous ranker | 1.000 | +0.000 [+0.000, +0.000] |
| no stemming | 1.000 | +0.000 [+0.000, +0.000] |
| keep query stopwords | 1.000 | +0.000 [+0.000, +0.000] |
| no identifier splitting | 0.997 | -0.003 [-0.009, +0.000] |
| no exact-name priority | 0.955 | -0.045 [-0.064, -0.028] |
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
| no exact-name priority | 0.943 | -0.057 [-0.087, -0.030] |
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
| no exact-name priority | 0.899 | -0.101 [-0.135, -0.072] |
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
| current | 0.900 | |
| previous ranker | 0.729 | -0.171 [-0.324, -0.043] |
| no stemming | 0.872 | -0.028 [-0.083, +0.000] |
| keep query stopwords | 0.907 | +0.007 [+0.000, +0.022] |
| no identifier splitting | 0.708 | -0.192 [-0.375, -0.033] |
| no exact-name priority | 0.900 | +0.000 [+0.000, +0.000] |
| class indexed by full source | 0.900 | +0.000 [+0.000, +0.000] |
| per-field saturation (linear) | 0.843 | -0.057 [-0.185, +0.033] |
| equal field weights | 0.861 | -0.039 [-0.150, +0.056] |

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
