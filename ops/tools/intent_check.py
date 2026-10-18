#!/usr/bin/env python3
"""INTENT coverage by script (01 §4 Step 8, 09 §5), so the pre-submit gate's numbers are never added up by hand.

  python3 tools/intent_check.py <draft or INTENT .md>

Reads the file's "## Inventory" table (| ID | Page | Label | Control | Required | … |) and "## Ledger" table
(| ID | Answer used | Source | Verified how | State |) and prints the coverage line to put in the INTENT:

  Required in inventory: X · verified required in ledger: Y · optional left blank: Z

Exit 0 when the gate's coverage part holds (every inventory ID is in the ledger, every required field is `verified`,
every optional one is `verified` or `optional-left-blank`); exit 1 with the reasons otherwise. Run it on the draft
before writing the INTENT (INTENT files are write-once). It checks coverage only: the page sweeps, the review-page
read-back and the approval are still the lane's to confirm.
"""
import re
import sys


def table(text, heading):
    """Rows of the first markdown table under '## <heading>…', as lists of stripped cells (header and rule dropped)."""
    m = re.search(r'^## ' + re.escape(heading) + r'[^\n]*\n(.*?)(?=^## |\Z)', text, re.S | re.M)
    if not m:
        return None
    rows = []
    for line in m.group(1).splitlines():
        if not line.startswith('|'):
            if rows:
                break
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if all(re.fullmatch(r':?-{2,}:?', c) for c in cells if c):
            continue
        rows.append(cells)
    return rows


def col(header, pat, default):
    """Index of the first header cell matching `pat`: lanes' tables don't all share one column order."""
    return next((i for i, h in enumerate(header) if re.search(pat, h, re.I)), default)


def ids(cell):
    """'P1.F10' → ['P1.F10']; a range 'P1.F10–F12' or 'P2.F15-F17' → each ID in it."""
    m = re.fullmatch(r'((?:P\d+\.)?[A-Z]+)(\d+)\s*[–-]\s*(?:(?:P\d+\.)?[A-Z]+)?(\d+)', cell)
    if m and int(m.group(3)) > int(m.group(2)):
        return [f'{m.group(1)}{i}' for i in range(int(m.group(2)), int(m.group(3)) + 1)]
    return [cell]


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    text = open(sys.argv[1], encoding='utf-8').read()
    inv, led = table(text, 'Inventory'), table(text, 'Ledger')
    if inv is None or led is None:
        print('ERROR: needs both a "## Inventory" and a "## Ledger" table')
        sys.exit(2)
    if not inv or not led:
        print('ERROR: an empty Inventory or Ledger table')
        sys.exit(2)
    ri, si = col(inv[0], r'^required', 4), col(led[0], r'^state', 4)
    required, state = {}, {}
    for r in inv[1:]:
        for fid in ids(r[0]) if r and r[0] else []:
            v = (r[ri] if len(r) > ri else '').lower()
            required[fid] = bool(re.match(r'(yes|y|required|true|\*|✓)', v))
    for r in led[1:]:
        for fid in ids(r[0]) if r and r[0] else []:
            state[fid] = (r[si] if len(r) > si else '').lower()
    problems = []
    for fid, req in required.items():
        s = state.get(fid)
        if s is None:
            problems.append(f'{fid}: in the inventory, not in the ledger')
        elif req and not s.startswith('verified'):
            problems.append(f'{fid}: required but ledger state is "{s}"')
        elif not req and not (s.startswith('verified') or s.startswith('optional-left-blank')):
            problems.append(f'{fid}: optional with state "{s}" (use verified or optional-left-blank)')
    extra = [f for f in state if f not in required]
    n_req = sum(required.values())
    n_ver = sum(1 for f, req in required.items() if req and state.get(f, '').startswith('verified'))
    n_blank = sum(1 for f, req in required.items() if not req and state.get(f, '').startswith('optional-left-blank'))
    print(f'Required in inventory: {n_req} · verified required in ledger: {n_ver} · optional left blank: {n_blank}')
    if extra:
        print('note: in the ledger but not the inventory: ' + ', '.join(extra))
    if problems:
        print('GATE NOT MET:')
        for p in problems:
            print('  ' + p)
        sys.exit(1)
    print('coverage OK')


if __name__ == '__main__':
    main()
