#!/usr/bin/env python3
"""Offline checks for jd_archive_api.name_problem, the Company/Title self-check that now runs before every JD Archive
append . Cases are the shapes seen mangled in practice, plus
name variants that are fine and must pass. Never touches the Sheet. Usage: python3 ops/tools/test_jd_archive_names.py"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jd_archive_api as ja  # noqa: E402
fails = []


def check(name, cond):
    print(('ok   ' if cond else 'FAIL ') + name)
    if not cond:
        fails.append(name)


P = ja.name_problem
check('attempt id in Title', P('JT-c8d1b6bd55', 'Barco, Territory Sales Manager', 'JT-c8d1b6bd55-a1',
                                              'Barco', 'Territory Sales Manager'))
check('split at a hyphen', P('4400000001', 'Epic, Entry', 'Level Technical Solutions Engineer',
                                     'Epic', 'Entry-Level Technical Solutions Engineer'))
check('company cut at its comma, Title starts "Inc.,"', P('4400000002', 'Hotwire Communications', 'LLC, Account Manager',
                                                         'Hotwire Communications, LLC', 'Account Manager'))
check("company's tail in Title", P('4400000003', 'TSP', 'a Syneos Health company (posting employer: X)',
                                   'TSP, a Syneos Health company', 'Specialty Sales Representative'))
check('Company holds the whole title', P('4400000004', 'Tata Consultancy Services, Client Partner (Senior', 'Utilities NA)',
                                         'Tata Consultancy Services', 'Client Partner'))
check('Title holds only the tail of the title', P('4400000005', 'Endress+Hauser Group (Field Instruments and Contro',
                                                  'Woodland, WA', 'Endress+Hauser Group', 'Inside Sales Engineer- Woodland, WA'))
check('fine: shorter company name', not P('4400000006', 'Lockton', 'Associate Account Executive, Employee Benefits',
                                          'Lockton Companies', 'Associate Account Executive, Employee Benefits'))
check('fine: annotated company', not P('4400000007', 'LINQX (LogistixIQ)', 'Account Executive - Logistics Technology',
                                       'LINQX', 'Account Executive - Logistics Technology'))
check('fine: JD page title differs from LinkedIn', not P('4400000008', 'Cloudflare', 'Senior Majors Account Executive',
                                                         'Cloudflare', 'Enterprise Account Executive'))
check('fine: longer title on the JD page', not P('4400000009', 'Nuix', 'Enterprise Sales Executive (Platform)',
                                                 'Nuix', 'Enterprise Sales Executive'))
check('fine: job not in the Queue, names look normal', not P('4400000010', 'Acme', 'Account Executive'))

print('\n' + ('ALL PASSED' if not fails else 'FAILURES:\n  ' + '\n  '.join(fails)))
sys.exit(1 if fails else 0)
