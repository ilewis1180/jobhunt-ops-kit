"""Simple A/B grading from a profile's title_any / title_exclude / boost lists. Used for stand-in profiles and the
unit tests; a profile that carries find-a-job-ai fields (core_skills, role_family) is graded by fajai_grade.py instead.

A = title matches a title_any term AND the title or description matches a boost term.
B = title matches a title_any term only.
None = rejected (title matches an exclude term, or no title match). Only A and B are posted.
"""
from .keys import normalize


def _hit(text, terms):
    t = " " + normalize(text) + " "
    return any((" " + normalize(x) + " ") in t for x in terms if normalize(x))


def grade(profile, title, description=""):
    if _hit(title, profile.get("title_exclude", [])):
        return None
    if not _hit(title, profile.get("title_any", [])):
        return None
    if _hit(title + " " + (description or ""), profile.get("boost", [])):
        return "A"
    return "B"
