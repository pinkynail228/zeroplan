# r3 — the catalog drops `process.pending`, which nothing raises since an undecided profile works as proposed

The whole Mac suite on baeb132 fails `tests.test_reference.ErrorFamilyTests.test_every_catalog_family_has_a_use_site
[process.pending]`: p093 (P3) made an undecided profile work as proposed (`Profile.settle`), so no code raises
`process.pending` any more, while terminal_planner/catalog.py still lists it and docs/REFERENCE.md documents it.

Change: remove the `process.pending` entry from catalog.py and regenerate docs/REFERENCE.md with
`python3.13 -m terminal_planner.catalog --write`. Any live text that still tells the owner to "accept or postpone"
before work can start goes with it.

Write-set: terminal_planner/catalog.py, docs/REFERENCE.md

Acceptance criteria:
- A1 The family is gone and the catalog test passes. Example: `grep -rn "process.pending" terminal_planner docs/REFERENCE.md`
  finds nothing; `tests.test_reference` passes.

Non-goals (reviewers must not require): the profile logic, other families, the first-start modal.

Conflict rule: if production code outside the write-set still raises `process.pending`, change nothing and end with
`conflict: <file:line>`.

Risk: low (catalog entry). DoD: `python3.13 devtools/fasttest.py tests.test_reference tests.test_docs`: exit 0.
