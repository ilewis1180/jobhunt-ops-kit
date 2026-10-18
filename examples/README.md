# examples/ — synthetic data in every file shape

Every row here is made up (fictional companies, reserved example domains, job ids in the 44000000xx range). They exist
so the tools and the dashboard can be exercised without real data, and so the column contracts in
`docs/11-data-model.md` have a concrete instance. `dashboard/sample-data/` assembles them into a data root.

| File | Shape |
|---|---|
| `raw.example.csv` | the Raw tab / scrape CSV (27 columns, 05 Step C) |
| `queue.example.csv` | the Queue tab (A–AA; L–AA are lookups in the sheet) |
| `outcomes.example.csv`, `outcomes-jt.example.csv` | one row per attempt (17 columns) |
| `timeline.example.csv`, `followups.example.csv` | the mail-matched timeline (16) and the operator's follow-ups (5) |
| `question-bank-observations.example.csv`, `question-bank.example.csv` | observations (14) and the rebuilt bank (8) |
| `jt-keys.example.csv` | job-tools keys (6) |
| `USAGE-R20260108-1300-orch.example.csv` | the token feed (16) |
| `board.example.csv` | a dispatch board (20) |
