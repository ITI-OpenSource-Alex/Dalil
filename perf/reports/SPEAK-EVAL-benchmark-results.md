# Speaking benchmark — measured results

**Exploratory, non-gating.** Speaker roles on the playlist items were assigned by heuristic rather than a second reviewer, and the official IELTS material's permission status is unreviewed. Plan section 6.3 permits a report of this kind and forbids treating it as a release gate.

Source transcripts are not reproduced. They are third-party material held locally under the permission recorded in the dataset manifest.

The two datasets are reported apart rather than pooled. The official set has the better labels and the weaker lane (transcript only, so Fluency judges flow from text with no timing and Pronunciation abstains for want of acoustics). The playlist has weaker labels and the full audio lane. One pooled number would describe neither.


## Dataset A — official IELTS samples

**Lane:** `scorer_only`

| item | examiner | ours | error | FC | LR | GRA | PR | status |
|---|---|---|---|---|---|---|---|---|
| `ielts-official-katsuharu` | 5.0 | — | — | _provider_error_ | 5.0 | 5.0 | _insufficient_evidence_ | partial |
| `ielts-official-tina` | 5.0 | 5.5 | +0.5 | 6.0 | 5.5 | 5.0 | _insufficient_evidence_ | partial |
| `ielts-official-maxim` | 6.0 | 6 | +0.0 | 6.0 | 6.0 | 6.0 | _insufficient_evidence_ | partial |
| `ielts-official-stephen` | 6.0 | 6 | +0.0 | 6.0 | 6.0 | 6.0 | _insufficient_evidence_ | partial |
| `ielts-official-michal` | 6.5 | 6 | -0.5 | 6.0 | 6.0 | 6.0 | _insufficient_evidence_ | partial |
| `ielts-official-alexandra` | 7.0 | — | — | — | — | — | — | not run |
| `ielts-official-hendrik` | 7.0 | 7 | +0.0 | 7.0 | 7.0 | 7.0 | _insufficient_evidence_ | partial |
| `ielts-official-aashish` | 7.5 | 7.5 | +0.0 | 8.0 | 7.0 | 8.0 | _insufficient_evidence_ | partial |
| `ielts-official-kopi` | 8.0 | 8 | +0.0 | 7.5 | 8.0 | 8.0 | _insufficient_evidence_ | partial |
| `ielts-official-monika` | 8.0 | 8 | +0.0 | 8.0 | 8.0 | 8.0 | _insufficient_evidence_ | partial |
| `ielts-official-kenn` | 8.5 | 8.5 | +0.0 | 8.0 | 9.0 | 8.5 | _insufficient_evidence_ | partial |
| `ielts-official-anuradha` | 9.0 | 8.5 | -0.5 | 8.5 | 8.5 | 8.0 | _insufficient_evidence_ | partial |

### Agreement (n=10)

| metric | value | 95% CI |
|---|---|---|
| exact agreement | 0.700 | — |
| within 0.5 band | 1.000 | [1.000, 1.000] |
| within 1.0 band | 1.000 | — |
| MAE | 0.150 | [0.000, 0.300] |
| RMSE | 0.274 | — |
| bias (signed) | -0.050 | [-0.200, 0.100] |
| over-scored | 0.100 | >1 band: 0.000 |
| under-scored | 0.200 | >1 band: 0.000 |
| quadratic weighted kappa | 0.972 | — |
| Spearman rho | 0.988 | — |

### Per-criterion means (no per-criterion reference exists)

| criterion | mean | n scored | n unavailable |
|---|---|---|---|
| FC | 7.10 | 10 | 1 |
| LR | 6.91 | 11 | 0 |
| GRA | 6.86 | 11 | 0 |
| PR | — | 0 | 11 |

## Dataset B — examiner channel recordings

**Lane:** `goa_audio`

| item | examiner | ours | error | FC | LR | GRA | PR | status |
|---|---|---|---|---|---|---|---|---|
| `yt-666eP6xBhzI` | 6.5 | 6.5 | +0.0 | 7.0 | 6.0 | 6.0 | 7.0 | complete |
| `yt-BFS1z24aZaM` | 6.5 | 7 | +0.5 | 7.5 | 6.5 | _provider_error_ | 7.0 | partial |
| `yt-OicvdCp5wrM` | 6.5 | — | — | 7.0 | 6.5 | _invalid_output_ | _invalid_output_ | partial |
| `yt-S8Y5D3RMBes` | 8.0 | 6.5 | -1.5 | _invalid_output_ | 6.5 | 6.0 | 7.0 | partial |
| `yt-ZDv9njERj0s` | 8.0 | 7.5 | -0.5 | 8.0 | 7.0 | 7.0 | 7.0 | complete |
| `yt-GKr5n9aa2Zw` | 8.5 | 7.5 | -1.0 | 8.0 | 7.0 | 7.0 | 7.5 | complete |
| `yt-lvF8q44170Q` | 8.5 | 7 | -1.5 | 7.0 | _provider_error_ | 6.5 | 7.0 | partial |
| `yt-4nrG6SHM-rY` | 9.0 | 7.5 | -1.5 | 7.5 | 7.0 | 7.0 | 7.5 | complete |
| `yt-IevmdO16GuE` | 9.0 | 7.5 | -1.5 | 8.0 | 7.0 | 7.0 | 7.5 | complete |
| `yt-gfKS-p7thDU` | 9.0 | — | — | _invalid_output_ | _invalid_output_ | _invalid_output_ | 7.5 | partial |

### Agreement (n=8)

| metric | value | 95% CI |
|---|---|---|
| exact agreement | 0.125 | — |
| within 0.5 band | 0.375 | [0.125, 0.750] |
| within 1.0 band | 0.500 | — |
| MAE | 1.000 | [0.562, 1.375] |
| RMSE | 1.146 | — |
| bias (signed) | -0.875 | [-1.375, -0.312] |
| over-scored | 0.125 | >1 band: 0.000 |
| under-scored | 0.750 | >1 band: 0.500 |
| quadratic weighted kappa | 0.276 | — |
| Spearman rho | 0.685 | — |

> n=8. Too few items for a stable estimate -- read the confidence interval, not the point estimate. This is a measurement of the available data, not a validation of the system.


### Per-criterion means (no per-criterion reference exists)

| criterion | mean | n scored | n unavailable |
|---|---|---|---|
| FC | 7.50 | 8 | 2 |
| LR | 6.69 | 8 | 2 |
| GRA | 6.64 | 7 | 3 |
| PR | 7.22 | 9 | 1 |

## Release gate

- **Official (scorer_only)** (n=10): `abstain`
  - Policy speaking-release-policy/v1-provisional is not approved, so no release decision was made. Its thresholds are provisional and carry no empirical rationale: human-human agreement has not been measured on this dataset. Enforcing them would produce a decision that looks like evidence.
- **Playlist (goa_audio)** (n=8): `abstain`
  - Policy speaking-release-policy/v1-provisional is not approved, so no release decision was made. Its thresholds are provisional and carry no empirical rationale: human-human agreement has not been measured on this dataset. Enforcing them would produce a decision that looks like evidence.
