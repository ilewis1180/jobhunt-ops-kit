# 03 — ATS quick reference

One line per applicant-tracking system the applier has met. `NOT OBSERVED` means pause-worthy, not an instruction. Every
entry gives the **confirmation method**, because Submit is confirmed by page text or URL, never a screenshot alone (00
rule 2). Keep one note file per ATS (`03-ATS/<ats>.md`: entry routes, widgets, quirks, consent wording) and read only
the files for the ATSs of your cards; `03-ATS/unknown-ats.md` is the procedure for an ATS with no file.

| ATS | Host tell | Login? | Parser | Confirmation |
|---|---|---|---|---|
| LinkedIn Easy Apply | `linkedin.com/jobs/view/<id>` modal (shadow DOM) | LinkedIn session | profile prefill: **overwrite contact fields**; remove prefilled work-history and education repeaters; pick the résumé from the stored list | modal "Your application was sent to <Company>!" + job page "Application submitted" |
| Workday | `<tenant>.wd<N>.myworkdayjobs.com` | **per tenant; assume gated** | "Autofill with Resume" (safe); check history after | "Application Submitted" modal + My Applications row |
| UltiPro / UKG | `recruiting*.ultipro.com/<CODE>` | gated, no guest path | — | NOT OBSERVED |
| SuccessFactors | `career<N>.successfactors.com` (often behind a career-site front) | gated (e-mail + password) | signed-in profile prefills contact | "Your application has been sent." + title "Successfully Applied to <title>" |
| Oracle Cloud CE | `<tenant>.fa.<region>.oraclecloud.com` | varies by tenant | résumé import button | a six-digit code after submit is normal |
| ADP WorkforceNow | `workforcenow.adp.com` | 2FA code after step 1 | — | NOT OBSERVED |
| Phenom | branded careers host | none seen | good (hidden input only) | redirect to `/applythankyou?status=success` |
| Greenhouse | `job-boards.greenhouse.io`, `boards.greenhouse.io`, embedded (`gh_jid`) | none | "Autofill my application": don't use | **redirect to `…/confirmation`**, "Thank you for applying." Public API gives the question list (`preflight.py`). |
| Talemetry | `apply.talemetry.com/application/<uuid>` (often in an iframe) | none | yes | none in flow: reload the URL → "already been completed" |
| PCRecruiter | `host.pcrecruiter.net` | none | none | "Thank you. Your information has been received." |
| Ashby | `jobs.ashbyhq.com/<co>/<uuid>/application` | none | none | green "Success" banner + XHR `ApiSubmit…` 200. Public API lists the board's jobs. |
| Lever | `jobs.lever.co/<co>/<uuid>/apply` | none | fills Current company: **clear it** | redirect to `/thanks`, "Application submitted!" Public API gives the posting. |
| Gusto | `jobs.gusto.com/postings/...` | none | — | "Success! Your application was submitted." |
| Paylocity | `recruiting.paylocity.com/Recruiting/Jobs/Apply/<id>` | none | inconsistent; "fill out with my resume" pre-checked: untick | redirect `/Recruiting/Jobs/Success/<id>` |
| BambooHR | `<co>.bamboohr.com/careers/<id>` | none | — | NOT OBSERVED (reCAPTCHA checkbox blocked) |
| Eightfold | `<co>.eightfold.ai/careers/job/<id>` | varies | varies | `/careers/apply/success`, "Thank you for your application" |
| Teamtailor | branded `careers.<co>.com/jobs/<id>-<slug>` | none | — | redirect `/applications/<uuid>/thanks/<hash>` |
| Workable | `apply.workable.com/<co>/j/<id>/apply/` | none | — | NOT OBSERVED |
| Zoho Recruit | `<co>.zohorecruit.com/jobs/Careers/<id>/<slug>` | none | "Autofill Application": don't use | NOT OBSERVED: a **visible image CAPTCHA** blocks submit (hand-off) |
| iCIMS | `<co>.icims.com/jobs/<id>/...` | often an account | damages history: upload first | "Thank you" page; the EEO step may be the closing "Continue" (00 rule 2) |
| Avature | `<co>.avature.net/...` | varies | damages history | a step beyond the last numbered one may be the Submit |
| SmartRecruiters | `jobs.smartrecruiters.com/<co>/<id>` | none | — | "Thank you" page |
| Jobvite | `jobs.jobvite.com/<co>/job/<id>` | none | — | in-flow text |
| Rippling, Comeet, Hireology, Paycor, JazzHR, Dayforce, Taleo, Brassring | by host | varies | Dayforce, Brassring: damage history | in-flow text or redirect; record what you see |

**Parser behaviour by tenant (07 live-form check item 5):** Workday, Dayforce, Brassring, Avature, iCIMS, UltiPro and
Lever damage or prefill the work history: upload the résumé first, then correct every row against the PDF.

**Never request** `linkedin.com` or `aplitrak.com` from a tool (a plain page load there once recorded an application);
`preflight.py` refuses both.

**Widgets:** Workday dropdowns are `button+listbox` (click, Escape, type the option text); Ashby yes/no are button pairs;
custom comboboxes need the option clicked, not typed; a `beforeunload` guard blocks `navigate` away from a half-filled
form (use the form's own Cancel).
