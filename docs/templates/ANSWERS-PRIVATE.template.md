# ANSWERS-PRIVATE — every answer and personal value (TEMPLATE)

Copy this file to the data root as `ANSWERS-PRIVATE.md` (git-ignored) and fill it in. It is the only place a personal
value lives. Cards, traces and capture files refer to it by section and key (`answers §Identity: mobile phone`,
`{APPLICATION_EMAIL}`) and never copy a value out of it (00 hard rule 8). Build your private PII pattern file
(`ops/tools/pii_patterns.example.json`) from the values here, so `pii_scan.py` catches any leak.

## Identity
- full_name · first_name · last_name · preferred_name · legal_name (if different)
- email (`{APPLICATION_EMAIL}`) · mobile_phone · linkedin_url · website

## Address
- street · city · state · zip · country · location (the one-line form "City, ST")

## Work authorization
- authorized to work in the target country: Yes/No · sponsorship needed: Yes/No · citizenship

## Attestations (answer truthfully; one row per statement a form may put to you)
| Statement | Answer |
|---|---|
| Information provided is accurate | Yes |
| Government or appointed official | … |
| Relatives at the employer | … |
| Non-compete in force | … |

## Screening (standing answers)
- how heard about the job: `Company Website`, else the job-site option
- relocation · travel (any percentage?) · on-call, weekend, physical requirements · extended hours
- background check · drug screen · driver's licence
- pay structure accepted: commission-only, contract (1099), part-time: Yes/No each
- years of experience by skill family (a table: skill → years, with the résumé roles that support it)

## Compensation
- desired base (text fields: `Negotiable`) · the figure for a required numeric field · how to answer a posted range

## Consents
- data processing · international transfer · privacy policy · terms · SMS (its own answer) · interview recording ·
  standard acknowledgements (at-will, waiver)

## Demographics
- decline wherever possible; where no decline option exists: gender · race/ethnicity · veteran · disability

## Résumé
- the rule that picks a résumé file per role family, and the file names in `Resume/`
- the LinkedIn stored-résumé name (Easy Apply picks from that list)

## Work history (what every form's history section must show)
- the roles exactly as on the résumé (employer, title, dates, location, state); any role deliberately left off; the
  current-role rule (no end date); the merge rule when a form caps the rows (07 live-form check item 2)

## Education
- school · degree · field · years; the closed-list fallback (e.g. "Other")

## References
- never recorded in any capture file; typed only into the form when the operator supplies them live

## Needs you (standing list of what the applier must always ask)
- an actual pay number when the form requires one and none is above · a demographic with no decline option ·
  a reference's details · any "willing to" not listed under Screening
