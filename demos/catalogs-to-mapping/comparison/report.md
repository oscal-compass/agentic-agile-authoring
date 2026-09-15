# NIST 800-53 → 800-171 Mapping: Generated vs. NIST CUI Overlay

- Reference (NIST CUI Overlay): **156 pairs** across 97 requirements
- Generated: **285 pairs** across 97 requirements

## Overall

| metric | value |
|---|---|
| Exact agreement | 144 |
| Reference-only (missed by generator) | 12 |
| Generated-only (extra vs. reference) | 141 |
| Relationship disagreements on shared pairs | 123 |
| **Precision** | 0.505 |
| **Recall** | 0.923 |
| **F1** | 0.653 |

Precision = |exact| / (|exact| + |generated-only|). Recall = |exact| / (|exact| + |reference-only|).

## Coverage by 800-171 family

| family | ref pairs | gen pairs | matched | recall |
|---|---:|---:|---:|---:|
| 03.01 | 31 | 52 | 28 | 90.32% |
| 03.02 | 4 | 4 | 4 | 100.00% |
| 03.03 | 12 | 24 | 12 | 100.00% |
| 03.04 | 13 | 34 | 13 | 100.00% |
| 03.05 | 11 | 20 | 9 | 81.82% |
| 03.06 | 7 | 14 | 7 | 100.00% |
| 03.07 | 6 | 8 | 5 | 83.33% |
| 03.08 | 8 | 17 | 8 | 100.00% |
| 03.09 | 3 | 4 | 3 | 100.00% |
| 03.10 | 6 | 12 | 6 | 100.00% |
| 03.11 | 6 | 10 | 6 | 100.00% |
| 03.12 | 4 | 6 | 4 | 100.00% |
| 03.13 | 14 | 25 | 14 | 100.00% |
| 03.14 | 6 | 16 | 5 | 83.33% |
| 03.15 | 19 | 18 | 14 | 73.68% |
| 03.16 | 3 | 7 | 3 | 100.00% |
| 03.17 | 3 | 14 | 3 | 100.00% |

## Top 10 requirements where the generator missed the most reference sources

| requirement | title | missed sources |
|---|---|---:|
| 03.15.01 | Policy and Procedures | 5 |
| 03.01.01 | Account Management | 2 |
| 03.14.03 | Security Alerts, Advisories, and Directives | 1 |
| 03.01.18 | Access Control for Mobile Devices | 1 |
| 03.07.04 | Maintenance Tools | 1 |
| 03.05.01 | User Identification and Authentication | 1 |
| 03.05.11 | Authentication Feedback | 1 |

## Top 10 requirements where the generator added the most extra sources

| requirement | title | extra sources |
|---|---|---:|
| 03.04.01 | Baseline Configuration | 6 |
| 03.04.03 | Configuration Change Control | 5 |
| 03.01.01 | Account Management | 5 |
| 03.14.06 | System Monitoring | 5 |
| 03.17.01 | Supply Chain Risk Management Plan | 5 |
| 03.01.05 | Least Privilege | 4 |
| 03.03.06 | Audit Record Reduction and Report Generation | 4 |
| 03.17.02 | Acquisition Strategies, Tools, and Methods | 4 |
| 03.13.01 | Boundary Protection | 4 |
| 03.05.02 | Device Identification and Authentication | 3 |

## Relationship distribution

Reference is uniformly `subset-of` (NIST convention: 800-171 is a tailored subset of 800-53).
Generator uses a mix:

| relationship | count |
|---|---:|
| intersects-with | 141 |
| equivalent-to | 108 |
| subset-of | 29 |
| superset-of | 7 |

On shared pairs, 123 have a different relationship label. Sample:

- `mp-4` → `03.08.01`: reference `subset-of`, generated `equivalent-to` (Media Storage)
- `cm-8` → `03.04.10`: reference `subset-of`, generated `equivalent-to` (System Component Inventory)
- `ra-5.2` → `03.11.02`: reference `subset-of`, generated `intersects-with` (Vulnerability Monitoring and Scanning)
- `cm-2.7` → `03.04.12`: reference `subset-of`, generated `equivalent-to` (System and Component Configuration for High-Risk Areas)
- `ac-18.3` → `03.01.16`: reference `subset-of`, generated `equivalent-to` (Wireless Access)
- `ac-20.1` → `03.01.20`: reference `subset-of`, generated `equivalent-to` (Use of External Systems)
- `cm-4.2` → `03.04.04`: reference `subset-of`, generated `intersects-with` (Impact Analyses)
- `cp-9.8` → `03.08.09`: reference `subset-of`, generated `equivalent-to` (System Backup – Cryptographic Protection)
- `ac-6` → `03.01.05`: reference `subset-of`, generated `equivalent-to` (Least Privilege)
- `ac-6.10` → `03.01.07`: reference `subset-of`, generated `equivalent-to` (Least Privilege – Privileged Functions)

## Notes on interpretation

- Reference-only pairs are pairs the NIST CUI Overlay asserts but the generator did not produce. These are false negatives against the authoritative baseline.
- Generated-only pairs are pairs the generator produced without NIST asserting them. They are review candidates, not evidence of NIST omission — some may be legitimate related-control links that NIST tailored out.
- Relationship disagreements: the reference labels every retained pair `subset-of`. The generator distinguishes `equivalent-to` / `intersects-with` / `superset-of`. On shared pairs, a generator label of `equivalent-to` is a stronger claim; `intersects-with` is weaker; `superset-of` inverts direction.
