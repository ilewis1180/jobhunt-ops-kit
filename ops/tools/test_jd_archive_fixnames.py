#!/usr/bin/env python3
"""Offline checks for jd_archive_api.plan_fixes, the planner behind `fix-names` : it
accepts only rows whose Job ID and current B/C still match the corrections CSV, and only fixes that pass the name
self-check. Never touches the Sheet. Usage: python3 ops/tools/test_jd_archive_fixnames.py"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jd_archive_api as ja  # noqa: E402
fails = []


def check(name, cond):
    print(('ok   ' if cond else 'FAIL ') + name)
    if not cond:
        fails.append(name)


def row(job, co, title):
    return [job, co, title, 'LinkedIn', 'Yes', '2026-10-16', 'https://x', '100', '', 'text']


SHEET = [list(ja.HEADER),
         row('4400000001', 'Acme', 'Account Executive'),
         row('4400000002', 'Hotwire Communications', 'LLC, Account Manager'),
         row('4400000003', 'Epic, Entry', 'Level Technical Solutions Engineer'),
         row('JT-c8d1b6bd55', 'Barco, Territory Sales Manager', 'JT-c8d1b6bd55-a1')]


def corr(n, job, b0, c0, b1, c1):
    return {'sheet_row': str(n), 'job_id': job, 'batch': 'x', 'problem': 'y', 'company_now': b0, 'title_now': c0,
            'company_fix': b1, 'title_fix': c1}


GOOD = [corr(3, '4400000002', 'Hotwire Communications', 'LLC, Account Manager', 'Hotwire Communications, LLC', 'Account Manager'),
        corr(4, '4400000003', 'Epic, Entry', 'Level Technical Solutions Engineer', 'Epic', 'Entry-Level Technical Solutions Engineer'),
        corr(5, 'JT-c8d1b6bd55', 'Barco, Territory Sales Manager', 'JT-c8d1b6bd55-a1', 'Barco', 'Territory Sales Manager')]
plan, problems = ja.plan_fixes(SHEET, GOOD)
check('three good corrections planned, none refused', not problems and [p[0] for p in plan] == [3, 4, 5]
      and plan[0][4:] == ('Hotwire Communications, LLC', 'Account Manager'))
check('row 2 (correct already) is not touched', all(p[0] != 2 for p in plan))

plan, problems = ja.plan_fixes(SHEET, [corr(3, '4400000009', 'Hotwire Communications', 'LLC, Account Manager', 'H', 'AM')])
check('refused: Job ID moved', not plan and problems and 'rows moved' in problems[0])
plan, problems = ja.plan_fixes(SHEET, [corr(3, '4400000002', 'Hotwire Communications, LLC', 'Account Manager', 'H', 'AM')])
check('refused: current B/C already changed', not plan and problems and 'already changed' in problems[0])
plan, problems = ja.plan_fixes(SHEET, [corr(5, 'JT-c8d1b6bd55', 'Barco, Territory Sales Manager', 'JT-c8d1b6bd55-a1', 'Barco', 'JT-c8d1b6bd55-a1')])
check('refused: the fix still fails the self-check', not plan and problems and 'self-check' in problems[0])
plan, problems = ja.plan_fixes(SHEET, [corr(99, '4400000002', 'a', 'b', 'c', 'd')])
check('refused: row outside the sheet', not plan and problems and 'outside' in problems[0])
plan, problems = ja.plan_fixes(SHEET, GOOD[:1] + GOOD[:1])
check('refused: a row listed twice', len(plan) == 1 and problems and 'twice' in problems[0])
plan, problems = ja.plan_fixes(SHEET, [corr(3, '4400000002', 'Hotwire Communications', 'LLC, Account Manager', '', 'AM')])
check('refused: empty fix value', not plan and problems and 'empty' in problems[0])

print('\n' + ('ALL PASSED' if not fails else 'FAILURES:\n  ' + '\n  '.join(fails)))
sys.exit(1 if fails else 0)
