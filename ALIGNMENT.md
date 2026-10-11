# Alignment Audit (Rules 85-100 / 16 items) — pptx-schema-lint

Audited: 2026-10-11, post round-2 iteration (v0.1.1). Evidence is reproducible.

| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | Safety/Ethics section | N/A | Non-security-research repo (QA/permissions tooling); no dangerous content in code or docs. |
| 2 | Privacy de-identification | PASS | grep scan `(sk-\|ghp_\|api_key\|password=)`: 0 real hits (1 false positive "ask-decision"); contact = hcac4735@agent.qq.com only; no real names. |
| 3 | Copyright boundary | PASS | 100% original code/text; no >50-word copied text from source repos (ideas restated, not quoted); MIT LICENSE present (zhengming contributors). |
| 4 | Fact-check annotations | PASS | Perf figures: self_test-measured with repro command in README FAQ; scaling claims marked [estimated]. |
| 5 | Confidence grading | PASS | README has 2 explicit Confidence labels (High/Medium) with one-line rationale each. |
| 6 | Minimal Fallback (PLAN B) | PASS | README "Minimal Fallback (PLAN B)" section: no-install degraded usage. |
| 7 | Quickstart time budget | PASS | Quickstart header states total time and per-step costs. |
| 8 | Rule-conflict arbitration | PASS | README "Design Trade-offs" states priority order explicitly. |
| 9 | Version changelog | PASS | CHANGELOG.md: v0.1.0 + v0.1.1, round-2 improvements itemized. |
| 10 | Exemption instruction (session rule) | N/A | Session-level governance; not applicable to static repo content. |
| 11 | External-knowledge cutoff | PASS | Time-sensitive statements (vocabulary, classes, tool names) tagged "as of 2026-10-11". |
| 12 | Explicit assumptions | PASS | README [Core Assumptions] lists 4 premises. |
| 13 | Logic-check triad | PASS | self_test 23/23 PASS (`python self_test.py -v` ~2.5 s): functional 8 + error paths 5 + extreme edges 6 + round-2 4 (fixture-built OOXML packages incl. corrupt zip/empty file). |
| 14 | Socratic FAQ | PASS | FAQ contains "When NOT to use this tool?" with concrete counter-scenarios. |
| 15 | Pareto iteration | PASS | v0.1.0->v0.1.1: new rule PSL008 + allowed-fonts fix + tests 19->23 (+21%); recorded in CHANGELOG. |
| 16 | Ultimate minimal entry | PASS | First paragraph ≤60 words, states what/who-needs-it with a judgment sentence. |

Additional: Limits & Second-order Effects section present per rule 16 (二阶思维).
