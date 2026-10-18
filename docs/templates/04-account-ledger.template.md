# 04 — Account ledger (TEMPLATE)

Which tenants are gated, where an account exists, and when it was last verified (01 §8.4). Lives in the data root
(not in git unless your tenant list is not sensitive to you). One row per tenant key (`dispatch.py` prints them).

| Tenant key | ATS | State | Verified | Notes |
|---|---|---|---|---|
| `workday-<tenant>` | Workday | account exists / needs account / guest ok | YYYY-MM-DD | sign-in confirmed on posting <JobID> |
| `<host>` | SuccessFactors | … | … | … |

States: `guest ok` (no account needed) · `account exists` (the operator signed in; the account menu was seen) ·
`needs account` (a wall was seen; the operator has not signed in) · `code gate` (a one-time code is sent on sign-in) ·
`blocked` (CAPTCHA or other hand-off before the form).
