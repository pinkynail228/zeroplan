# docs/product: what zplan is and why

The source for the public README, the landing page and any newcomer (person or agent) who needs to know what
zplan is for before reading code. Other docs say *how* (docs/USER_FLOW.md, docs/INSTALLATION.md, docs/REFERENCE.md);
these say *why* and *what*.

| File | Answers | Feeds |
|---|---|---|
| VISION.md | What problem, for whom, what zplan is and is not, principles | README top, landing hero |
| PRFAQ.md | The announcement and the hard questions | landing FAQ |
| FEATURES.md | What zplan does today, by job, with maturity | README "Features", landing |
| BOUNDARY.md | What Zeroshot does, what zplan adds, the invariants | README "How it works", agent onboarding |
| COMPREHENSION_TEST.md | Ten questions a reader of this folder must answer | check after every edit here |

Rules for this folder:
- Every claim is true of the current release or is marked *planned* with its release. No marketing beyond the evidence.
- Features and statuses come from code and tests, not from older docs. When a release changes them, update FEATURES.md
  in the same change.
- Plain English, short sentences, no internal ids (run ids, incident numbers, task names).
- After an edit, run the comprehension test with a fresh agent that reads only this folder.
