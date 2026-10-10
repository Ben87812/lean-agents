# Cuts

Every change tried to make runs cheaper, with its benchmark result. A cut merges only if the hidden tests pass as often or more, total tokens fall by more than 10% against the current plugin, and the drop shows in the cause it targets. Single runs per arm unless noted.

| Date | Cut | Tier | Hidden tests (lean → cut) | Tokens (lean → cut) | Targeted cause (lean → cut) | Verdict |
|---|---|---|---|---|---|---|
| 2026-10-10 | Module notes (`cut/module-notes`) | long | 1/1 → 0/1 | 3.8M → 3.7M (−3%) | re-reads 0.00M → 0.03M | Rejected: under the 10% bar, and graded as a fail. Its own test file used a helper that the hidden test file replaces, so the package did not compile; with that file set aside, its code passed every hidden test. Re-reads were already near zero in the lean arm, so there was little for notes to save on a single task. Worth retrying on a tier with several tasks in one area. |
