# Track B measurement: sub-1B models against the deterministic baseline

Run 2026-10-21 15:51 on papichulo-OptiPlex-790, 4 threads. Cases: `scripts/bench_cases.json` (12 documents, 8 commands). Protocol: `docs/ASSIST-PLAN.md`.

Scoring: a field the document does not state must come back empty. **wrong** means the model invented a value; **blank** means it refused one that was there. An invented value is the failure that matters in a compliance record.

| Run | Size | Load | RSS | Median latency | p90 | tok/s | Doc accuracy | wrong | blank | Intent | Quantity | Determinism |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| deterministic baseline | - MB | - s | - MB | 0.07 ms | - ms | - | 98% | 0 | 1 | 8/8 | 8/8 | n/a |
| granite-350m | - MB | - s | - MB | - ms | - ms | - | 89% | 3 | 4 | 7/8 | 8/8 | n/a |
| smollm2-360m | - MB | - s | - MB | - ms | - ms | - | 85% | 4 | 6 | 7/8 | 8/8 | n/a |
| qwen3-0.6b | - MB | - s | - MB | - ms | - ms | - | 96% | 0 | 3 | 7/8 | 8/8 | n/a |

## Per-field detail

### deterministic baseline

| Case | Field | Verdict |
|---|---|---|
| coa-1 | product_name | correct |
| coa-1 | thc_percent | correct |
| coa-1 | cbd_percent | correct |
| coa-1 | lab | correct |
| coa-1 | tested_on | correct |
| coa-1 | sample_id | correct |
| coa-2 | product_name | correct |
| coa-2 | thc_percent | correct |
| coa-2 | cbd_percent | correct |
| coa-2 | lab | correct |
| coa-2 | tested_on | correct |
| coa-2 | sample_id | correct |
| coa-3 | product_name | correct |
| coa-3 | thc_percent | correct |
| coa-3 | cbd_percent | correct |
| coa-3 | lab | correct |
| coa-3 | tested_on | correct |
| coa-3 | sample_id | correct |
| coa-4 | product_name | correct |
| coa-4 | thc_percent | correct |
| coa-4 | cbd_percent | correct |
| coa-4 | lab | blank |
| coa-4 | tested_on | correct |
| coa-4 | sample_id | correct |
| coa-5 | product_name | correct |
| coa-5 | thc_percent | correct |
| coa-5 | cbd_percent | correct |
| coa-5 | lab | correct |
| coa-5 | tested_on | correct |
| coa-5 | sample_id | correct |
| coa-6 | product_name | correct |
| coa-6 | thc_percent | correct |
| coa-6 | cbd_percent | correct |
| coa-6 | lab | correct |
| coa-6 | tested_on | correct |
| coa-6 | sample_id | correct |
| inv-1 | buyer | correct |
| inv-1 | seller | correct |
| inv-1 | quantity | correct |
| inv-1 | unit_price | correct |
| inv-1 | invoice_date | correct |
| inv-2 | buyer | correct |
| inv-2 | seller | correct |
| inv-2 | quantity | correct |
| inv-2 | unit_price | correct |
| inv-2 | invoice_date | correct |
| inv-3 | buyer | correct |
| inv-3 | seller | correct |
| inv-3 | quantity | correct |
| inv-3 | unit_price | correct |
| inv-3 | invoice_date | correct |
| inv-4 | buyer | correct |
| inv-4 | seller | correct |
| inv-4 | quantity | correct |
| inv-4 | unit_price | correct |
| inv-4 | invoice_date | correct |
| inv-5 | buyer | correct |
| inv-5 | seller | correct |
| inv-5 | quantity | correct |
| inv-5 | unit_price | correct |
| inv-5 | invoice_date | correct |
| inv-6 | buyer | correct |
| inv-6 | seller | correct |
| inv-6 | quantity | correct |
| inv-6 | unit_price | correct |
| inv-6 | invoice_date | correct |

| Command | Intent | Quantity |
|---|---|---|
| cmd-1 | yes | yes |
| cmd-2 | yes | yes |
| cmd-3 | yes | yes |
| cmd-4 | yes | yes |
| cmd-5 | yes | yes |
| cmd-6 | yes | yes |
| cmd-7 | yes | yes |
| cmd-8 | yes | yes |

### granite-350m

| Case | Field | Verdict |
|---|---|---|
| coa-1 | product_name | correct |
| coa-1 | thc_percent | correct |
| coa-1 | cbd_percent | correct |
| coa-1 | lab | correct |
| coa-1 | tested_on | correct |
| coa-1 | sample_id | correct |
| coa-2 | product_name | correct |
| coa-2 | thc_percent | correct |
| coa-2 | cbd_percent | correct |
| coa-2 | lab | correct |
| coa-2 | tested_on | blank |
| coa-2 | sample_id | blank |
| coa-3 | product_name | correct |
| coa-3 | thc_percent | correct |
| coa-3 | cbd_percent | correct |
| coa-3 | lab | blank |
| coa-3 | tested_on | correct |
| coa-3 | sample_id | correct |
| coa-4 | product_name | correct |
| coa-4 | thc_percent | correct |
| coa-4 | cbd_percent | correct |
| coa-4 | lab | correct |
| coa-4 | tested_on | correct |
| coa-4 | sample_id | correct |
| coa-5 | product_name | correct |
| coa-5 | thc_percent | correct |
| coa-5 | cbd_percent | correct |
| coa-5 | lab | correct |
| coa-5 | tested_on | correct |
| coa-5 | sample_id | blank |
| coa-6 | product_name | wrong |
| coa-6 | thc_percent | correct |
| coa-6 | cbd_percent | correct |
| coa-6 | lab | correct |
| coa-6 | tested_on | correct |
| coa-6 | sample_id | correct |
| inv-1 | buyer | correct |
| inv-1 | seller | correct |
| inv-1 | quantity | correct |
| inv-1 | unit_price | correct |
| inv-1 | invoice_date | correct |
| inv-2 | buyer | correct |
| inv-2 | seller | correct |
| inv-2 | quantity | correct |
| inv-2 | unit_price | correct |
| inv-2 | invoice_date | correct |
| inv-3 | buyer | correct |
| inv-3 | seller | correct |
| inv-3 | quantity | correct |
| inv-3 | unit_price | correct |
| inv-3 | invoice_date | correct |
| inv-4 | buyer | wrong |
| inv-4 | seller | wrong |
| inv-4 | quantity | correct |
| inv-4 | unit_price | correct |
| inv-4 | invoice_date | correct |
| inv-5 | buyer | correct |
| inv-5 | seller | correct |
| inv-5 | quantity | correct |
| inv-5 | unit_price | correct |
| inv-5 | invoice_date | correct |
| inv-6 | buyer | correct |
| inv-6 | seller | correct |
| inv-6 | quantity | correct |
| inv-6 | unit_price | correct |
| inv-6 | invoice_date | correct |

| Command | Intent | Quantity |
|---|---|---|
| cmd-1 | yes | yes |
| cmd-2 | no | yes |
| cmd-3 | yes | yes |
| cmd-4 | yes | yes |
| cmd-5 | yes | yes |
| cmd-6 | yes | yes |
| cmd-7 | yes | yes |
| cmd-8 | yes | yes |

### smollm2-360m

| Case | Field | Verdict |
|---|---|---|
| coa-1 | product_name | wrong |
| coa-1 | thc_percent | correct |
| coa-1 | cbd_percent | correct |
| coa-1 | lab | correct |
| coa-1 | tested_on | correct |
| coa-1 | sample_id | correct |
| coa-2 | product_name | correct |
| coa-2 | thc_percent | correct |
| coa-2 | cbd_percent | correct |
| coa-2 | lab | correct |
| coa-2 | tested_on | correct |
| coa-2 | sample_id | correct |
| coa-3 | product_name | correct |
| coa-3 | thc_percent | correct |
| coa-3 | cbd_percent | correct |
| coa-3 | lab | blank |
| coa-3 | tested_on | blank |
| coa-3 | sample_id | correct |
| coa-4 | product_name | correct |
| coa-4 | thc_percent | correct |
| coa-4 | cbd_percent | correct |
| coa-4 | lab | blank |
| coa-4 | tested_on | blank |
| coa-4 | sample_id | correct |
| coa-5 | product_name | correct |
| coa-5 | thc_percent | correct |
| coa-5 | cbd_percent | correct |
| coa-5 | lab | blank |
| coa-5 | tested_on | blank |
| coa-5 | sample_id | correct |
| coa-6 | product_name | correct |
| coa-6 | thc_percent | correct |
| coa-6 | cbd_percent | correct |
| coa-6 | lab | wrong |
| coa-6 | tested_on | correct |
| coa-6 | sample_id | correct |
| inv-1 | buyer | correct |
| inv-1 | seller | correct |
| inv-1 | quantity | correct |
| inv-1 | unit_price | correct |
| inv-1 | invoice_date | correct |
| inv-2 | buyer | correct |
| inv-2 | seller | correct |
| inv-2 | quantity | correct |
| inv-2 | unit_price | correct |
| inv-2 | invoice_date | correct |
| inv-3 | buyer | correct |
| inv-3 | seller | correct |
| inv-3 | quantity | correct |
| inv-3 | unit_price | correct |
| inv-3 | invoice_date | correct |
| inv-4 | buyer | wrong |
| inv-4 | seller | correct |
| inv-4 | quantity | correct |
| inv-4 | unit_price | correct |
| inv-4 | invoice_date | correct |
| inv-5 | buyer | correct |
| inv-5 | seller | correct |
| inv-5 | quantity | correct |
| inv-5 | unit_price | wrong |
| inv-5 | invoice_date | correct |
| inv-6 | buyer | correct |
| inv-6 | seller | correct |
| inv-6 | quantity | correct |
| inv-6 | unit_price | correct |
| inv-6 | invoice_date | correct |

| Command | Intent | Quantity |
|---|---|---|
| cmd-1 | yes | yes |
| cmd-2 | yes | yes |
| cmd-3 | no | yes |
| cmd-4 | yes | yes |
| cmd-5 | yes | yes |
| cmd-6 | yes | yes |
| cmd-7 | yes | yes |
| cmd-8 | yes | yes |

### qwen3-0.6b

| Case | Field | Verdict |
|---|---|---|
| coa-1 | product_name | correct |
| coa-1 | thc_percent | correct |
| coa-1 | cbd_percent | correct |
| coa-1 | lab | correct |
| coa-1 | tested_on | correct |
| coa-1 | sample_id | correct |
| coa-2 | product_name | correct |
| coa-2 | thc_percent | correct |
| coa-2 | cbd_percent | correct |
| coa-2 | lab | correct |
| coa-2 | tested_on | correct |
| coa-2 | sample_id | blank |
| coa-3 | product_name | correct |
| coa-3 | thc_percent | correct |
| coa-3 | cbd_percent | correct |
| coa-3 | lab | correct |
| coa-3 | tested_on | correct |
| coa-3 | sample_id | correct |
| coa-4 | product_name | correct |
| coa-4 | thc_percent | correct |
| coa-4 | cbd_percent | correct |
| coa-4 | lab | correct |
| coa-4 | tested_on | correct |
| coa-4 | sample_id | correct |
| coa-5 | product_name | correct |
| coa-5 | thc_percent | correct |
| coa-5 | cbd_percent | correct |
| coa-5 | lab | correct |
| coa-5 | tested_on | correct |
| coa-5 | sample_id | correct |
| coa-6 | product_name | correct |
| coa-6 | thc_percent | correct |
| coa-6 | cbd_percent | correct |
| coa-6 | lab | correct |
| coa-6 | tested_on | correct |
| coa-6 | sample_id | correct |
| inv-1 | buyer | blank |
| inv-1 | seller | correct |
| inv-1 | quantity | correct |
| inv-1 | unit_price | correct |
| inv-1 | invoice_date | correct |
| inv-2 | buyer | correct |
| inv-2 | seller | correct |
| inv-2 | quantity | correct |
| inv-2 | unit_price | correct |
| inv-2 | invoice_date | correct |
| inv-3 | buyer | correct |
| inv-3 | seller | correct |
| inv-3 | quantity | correct |
| inv-3 | unit_price | correct |
| inv-3 | invoice_date | correct |
| inv-4 | buyer | correct |
| inv-4 | seller | correct |
| inv-4 | quantity | correct |
| inv-4 | unit_price | correct |
| inv-4 | invoice_date | correct |
| inv-5 | buyer | blank |
| inv-5 | seller | correct |
| inv-5 | quantity | correct |
| inv-5 | unit_price | correct |
| inv-5 | invoice_date | correct |
| inv-6 | buyer | correct |
| inv-6 | seller | correct |
| inv-6 | quantity | correct |
| inv-6 | unit_price | correct |
| inv-6 | invoice_date | correct |

| Command | Intent | Quantity |
|---|---|---|
| cmd-1 | no | yes |
| cmd-2 | yes | yes |
| cmd-3 | yes | yes |
| cmd-4 | yes | yes |
| cmd-5 | yes | yes |
| cmd-6 | yes | yes |
| cmd-7 | yes | yes |
| cmd-8 | yes | yes |

