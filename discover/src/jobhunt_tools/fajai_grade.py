"""Real A-F grading from the patched find-a-job-ai (vendor/find_a_job_ai/daily_job_search.py).

The vendored file is NOT in this repository (upstream publishes no licence): run vendor/find_a_job_ai/fetch.sh once,
which clones the upstream commit and applies sales-grading.patch.

Use grade_row() for profiles that carry find-a-job-ai fields (core_skills, role_family). The older
grade.py title/boost grader stays for the unit tests and for stand-in profiles.
"""
import importlib.util
from pathlib import Path

_V = Path(__file__).resolve().parent.parent.parent / "vendor" / "find_a_job_ai"
_mod = None


def _fajai():
    global _mod
    if _mod is None:
        if not (_V / "daily_job_search.py").exists():
            raise FileNotFoundError(f"{_V / 'daily_job_search.py'} is missing: run {_V / 'fetch.sh'} first (see vendor/find_a_job_ai/SOURCE.md)")
        spec = importlib.util.spec_from_file_location("fajai_daily_job_search", _V / "daily_job_search.py")
        _mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_mod)
    return _mod


def is_real_profile(profile):
    return "core_skills" in profile and "role_family" in profile


def build_ctx(profile):
    m = _fajai()
    p = dict(profile)
    for k, v in (("years_experience", 3), ("core_skills", {}), ("secondary_skills", {}), ("core_stack_max", 40),
                 ("secondary_stack_cap", 16), ("language_requirements", {}), ("work_authorization", {}),
                 ("work_location_preference", "any")):
        p.setdefault(k, v)
    wa = p["work_authorization"]
    dq, pos = m.build_workauth_patterns(wa)
    return {
        "lang_req": p["language_requirements"], "workauth_disqualify": dq, "workauth_positive": pos,
        "workauth_is_citizen": bool(wa.get("is_citizen")),
        "workauth_country": wa.get("target_country") or "the target country",
        "years_experience": p["years_experience"],
        "core_patterns": m.build_stack_patterns(p["core_skills"]),
        "secondary_patterns": m.build_stack_patterns(p["secondary_skills"]),
        "core_max": p["core_stack_max"], "secondary_cap": p["secondary_stack_cap"],
        "secondary_names": list(p["secondary_skills"].keys()),
        "location_pref": p["work_location_preference"],
        "seniority_stretch": m.build_seniority_stretch(p), "role_family": m.build_role_family(p),
    }


def grade_row(ctx, title, description="", company="", location="", url=""):
    """Returns (letter or '', score or '', exclusion_reason or ''). Only A/B are candidates downstream."""
    m = _fajai()
    job = {"title": title or "", "company": company, "location": location, "job_url": url,
           "description": m.unescape_markdown(description or ""), "tags": [], "language_tag": None,
           "sponsorship_tag": None}
    if not m.evaluate(job, ctx):
        return "", "", job.get("exclusion_reason", "")
    return job["grade"], job["score"], ""
