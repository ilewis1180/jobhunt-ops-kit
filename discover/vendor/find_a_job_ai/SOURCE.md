# find-a-job-ai (vendored grader): not included, fetched on demand

`fajai_grade.py` runs the A–F grader from `michaelshirley1/find-a-job-ai` (`scripts/daily_job_search.py`, commit
`d50233e`) with a small patch that makes it usable for non-engineering roles:

- `profile_id`: a separate seen-jobs state file and report per profile;
- `seniority_stretch_terms`: which title words count as a stretch (`[]` disables the built-in list);
- `role_family` `{other, adjacent, core}`: title-only matching, and a title matching none of `core` is capped at D.

The upstream repository publishes **no licence**, so its file is not redistributed here (it is git-ignored). Run
`fetch.sh` once: it clones the pinned commit into a temp folder, copies `daily_job_search.py` next to this file and
applies `sales-grading.patch` (the patch is this kit's own change). Without it, `run_search.py` falls back to the
simple title/boost grader in `grade.py`.

Reading the grades: the language slot auto-awards 20 for a market without a language requirement and citizenship
auto-awards 20, so every listing starts at 40 + role (10) + seniority (10). Grades run high; use them to rank within
a report, not as absolutes.
