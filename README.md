# pptx-schema-lint

A structural quality linter for OOXML packages (PPTX first, generic-capable).
It catches placeholder residue, off-theme fonts, dangling relationships, and
unresolved references — the machine-checkable part of "is this deck actually
done?" — before a human ever opens it. Not a renderer, not an AI: a linter.

**Confidence: High (>=85%)** for the seven structural rules on OOXML-as-ZIP;
**Medium (60-79%)** that theme-derived font allowlists match real-world decks.

## Problem

AI decks now output *native, editable* PPTX — native shapes, live charts,
real text runs. The overlooked angle of that wave: nothing verifies the
structural quality of the output. A generated deck can render fine while
containing `Click to add title` placeholder residue, a Comic Sans run that
leaked from a template, or a chart relationship pointing at a part that was
never written — silent breakage a human finds mid-presentation. Visual
QA cannot scale to a pipeline producing hundreds of decks; a lint step can.

Repositioned as a **generic OOXML linter**: the package rules (zip structure,
relationships, text residue, font allowlist) apply to any `.pptx/.docx/.xlsx`
container, not one tool's output.

## How it works

Opens the package as a ZIP, parses every XML part with `xml.etree`, and runs
7 rules (each tagged, severity error|warn):

| Rule | Catches |
|---|---|
| PSL001 | placeholder residue text ("Click to add ...") |
| PSL002 | fonts outside the theme/allowlist |
| PSL003 | relationship targets pointing to missing parts (broken charts/images) |
| PSL004 | missing required parts, unparseable XML |
| PSL005 | `r:id`/`r:embed` attributes with no matching relationship |
| PSL006 | TODO / FIXME / lorem-ipsum residue (warn) |
| PSL007 | whitespace-only text runs (warn) |
| PSL008 | duplicate part names in the zip (fatal to some readers; reported as harness error) |

Duplicate detection note: PSL008 is surfaced as an `error:` message with exit
code 2 because a package with collapsed duplicate parts cannot be linted
meaningfully at all.

Exit codes: `0` clean, `1` violations (warnings too with `--strict`), `2`
harness error (corrupt/empty input) — drops straight into CI.

## Quickstart (~1 min)

```bash
# Lint one deck (~0.1 s)
python pptx_schema_lint.py deck.pptx

# CI gate with custom brand fonts, warnings fail the build (~0.1 s)
python pptx_schema_lint.py deck.pptx --allowed-fonts "Inter,JetBrains Mono" --strict

# Machine-readable report
python pptx_schema_lint.py deck.pptx --json
```

## Why not X

| Alternative | Why not here |
|---|---|
| Open the deck in PowerPoint/LibreOffice manually | Does not scale to pipelines; human-eyeball misses rel-level breakage; no exit codes. |
| python-pptx-based validators | python-pptx **fails to open** many structurally-broken packages — exactly the ones you most want flagged. This linter reads raw parts and reports what it can. |
| OOXML XSD schema validation | Validates well-formedness against huge schemas, but not *quality*: placeholder residue and font drift are schema-valid garbage. |
| Generic XML linters (xmllint) | No OOXML package semantics: no rels resolution, no theme fonts, no placeholder vocabulary. |

## Minimal Fallback (PLAN B)

No Python? The first two checks degrade to shell one-liners:

```bash
# Is it even a zip with a content-types part?
unzip -l deck.pptx | grep -q "Content_Types" && echo OK || echo BROKEN
# Placeholder residue in any part (crude, catches most cases)
unzip -p deck.pptx "*.xml" | grep -c "Click to add"
```

You lose rels graph, font allowlists, and severity levels — but you keep a
smoke gate with nothing installed.

## Design Trade-offs

Priority: **never-crash reporting > recall of structural breakage > speed**.

- Lint raw parts instead of loading via python-pptx: more work, but the tool
  stays functional on the damaged packages that matter most.
- Font rule derives the allowlist from the package's own theme by default:
  zero configuration, at the cost of "a deck is consistent with a bad theme".
  `--allowed-fonts` replaces the theme list entirely (theme parts themselves
  are never flagged — they define the baseline).
- Warnings do not fail by default: TODO/empty-run residue is noisy; teams
  opt into strictness (`--strict`) rather than being forced to disable.

## Limits & Second-order Effects

- Lint-clean ≠ good-looking: layout, contrast, and narrative quality stay
  human judgment. Widespread lint adoption may normalize "passes = ship"
  and quietly drop human review of visual quality.
- The theme-derived font allowlist can launder one template's bad fonts into
  every deck built from it. Audit themes, not just decks.
- Rules are English-vocabulary-based ("Click to add"); localized Office UI
  strings will not match — contributions for i18n patterns welcome.

## FAQ

**Q: When NOT to use this tool?**
A: When you need to verify *rendering fidelity* (export to PNG and diff), or
evaluate content quality (structure is not story). Also skip it for packages
you know are schema-invalid by design — it reports damage, it does not repair.

**Q: Does it modify files?**
A: Never. Read-only analysis.

**Q: Does it work on .docx/.xlsx?**
A: Yes, with `--profile generic`: package-level rules (rels, parts, text
residue, fonts) are container-agnostic. PPTX-specific part requirements are
skipped. Some rules (PSL007) apply to any `w:t`/`t` text as well.

**Q: How fast?**
A: Self-test measured: 23 tests including a 52-part fixture package in ~2.5 s
total (`python self_test.py -v` reproduces); rule cost is linear in XML size
[estimated].

## [Core Assumptions]

1. OOXML packages are ZIPs of XML parts whose relationships live in
   `_rels/*.rels` — stable across the formats, per ECMA-376 structure as of
   2026-10-11.
2. Structural defects (dangling rels, placeholder residue) correlate with
   real user-facing breakage strongly enough to gate on.
3. Teams can name their legitimate fonts (theme fonts are the default
   answer); if they cannot, the font rule can be disabled by absence of
   theme data.
4. Violations are advisory until wired into CI — the tool's value comes from
   being run on every deck-producing change.

---
Contact: hcac4735@agent.qq.com · License: MIT · Rule vocabulary as of 2026-10-11.
