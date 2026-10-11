# Changelog — pptx-schema-lint

## v0.1.1 — 2026-10-11 (round-2 iteration: rule + tests)

### Added
- **PSL008 duplicate-part**: packages containing the same part name twice
  (zip collapses to the last entry; some OOXML readers break) are reported
  as a harness error with the offending names.
- Round-2 tests: duplicate-part detection, `--allowed-fonts` override
  semantics, font-rule auto-disable without theme, `--strict` CLI exit path.
  Test count 19 → 23 (+21%).

### Fixed
- Explicit `--allowed-fonts` no longer flags fonts *inside theme parts*
  (the theme defines the baseline; flagging it made the override unusable).

### Changed
- README: PSL008 documented; allowed-fonts semantics clarified; perf figure
  re-measured (23 tests in ~2.5 s).

## v0.1.0 — 2026-10-11

Initial draft: 7 rules (PSL001 placeholder residue, PSL002 font allowlist
from theme, PSL003 dangling relationship targets, PSL004 missing/unparseable
required parts, PSL005 unresolved r:id/r:embed, PSL006 TODO/lorem residue
[word-boundary matched], PSL007 whitespace-only runs), `--profile
pptx|generic`, severity model (error/warn, `--strict`), `--json` output,
exit codes 0/1/2, fixture-driven 19-test battery.
