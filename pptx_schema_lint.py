#!/usr/bin/env python3
"""pptx-schema-lint: structural quality linter for OOXML packages (PPTX first).

Positioning: a *generic OOXML package linter*. It opens the ZIP container,
parses the XML parts with the stdlib, and reports structural problems that
break editability or professionalism:

  PSL001 placeholder-residue    default placeholder text left in slides
  PSL002 font-not-allowed       run fonts outside the theme/allowlist
  PSL003 dangling-relationship  a rel target points to a missing part
  PSL004 missing-required-parts [Content_Types].xml / main document absent
  PSL005 unresolved-rid         r:id / r:embed attribute with no matching rel
  PSL006 todo-residue           TODO / FIXME / lorem-ipsum text
  PSL007 empty-text-run         visible empty <a:t> runs (layout noise)
  PSL008 duplicate-part         the same part name appears twice in the zip

Exit codes: 0 clean (or warnings only), 1 violations found, 2 harness error.
Pure standard library.
"""
from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

PLACEHOLDER_PATTERNS = (
    "click to add", "click to edit", "click to enter",
)
# word-boundary match so "todolist"/"fixmed" never false-positive
TODO_RE = re.compile(r"\b(todo|fixme|xxx|tbd)\b|lorem ipsum", re.IGNORECASE)
PLACEHOLDER_FONT_HINTS = ("+mj-lt", "+mn-lt")  # theme-resolved fonts are fine

REQUIRED_PARTS_ANY = ("[Content_Types].xml",)
REQUIRED_PARTS_PPTX = ("ppt/presentation.xml",)

REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _attrs(elem):
    for k, v in elem.attrib.items():
        yield _local(k), k, v


def _part_dir(part: str) -> str:
    return posixpath.dirname(part)


def _resolve_target(part: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(_part_dir(part), target))


class LintError(Exception):
    """Raised when the package cannot be linted at all (exit code 2)."""


def load_package(path) -> dict:
    """Open an OOXML zip and return {name: bytes}. Raises LintError on failure."""
    p = Path(path)
    if not p.is_file():
        raise LintError(f"file not found: {p}")
    data = p.read_bytes()
    if len(data) == 0:
        raise LintError("file is empty (zero bytes)")
    try:
        with zipfile.ZipFile(p) as zf:
            names = zf.namelist()
            parts = {n: zf.read(n) for n in names}
    except zipfile.BadZipFile as exc:
        raise LintError(f"not a valid zip/OOXML package: {exc}") from exc
    # Duplicate part names are fatal to some OOXML readers; zipfile keeps the
    # last entry, so surface them before the dict collapses them.
    seen, dupes = set(), []
    for n in names:
        if n in seen and n not in dupes:
            dupes.append(n)
        seen.add(n)
    if dupes:
        raise LintError(f"duplicate part names in package: {', '.join(dupes[:5])}")
    return parts


def parse_xml(name: str, data: bytes):
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise LintError(f"part {name} is not parseable XML: {exc}") from exc


def collect_rels(parts: dict) -> dict:
    """Return {part: {rel_id: resolved_target}} for every _rels/*.rels file."""
    rels = {}
    for name in parts:
        if not name.endswith(".rels"):
            continue
        if name == "_rels/.rels":
            owner = ""  # package-level relationships
        else:
            # ppt/slides/_rels/slide1.xml.rels -> ppt/slides/slide1.xml
            owner = name[:-len(".rels")].replace("_rels/", "", 1)
        root = parse_xml(name, parts[name])
        mapping = {}
        for rel in root.iter():
            if _local(rel.tag) != "Relationship":
                continue
            attrs = {local: v for local, _, v in _attrs(rel)}
            rid = attrs.get("Id")
            target = attrs.get("Target", "")
            mode = attrs.get("TargetMode", "Internal")
            if rid is None:
                continue
            mapping[rid] = None if mode == "External" else _resolve_target(owner or "", target)
        rels[owner or ""] = mapping
    return rels


def theme_fonts(parts: dict):
    fonts = set()
    for name, data in parts.items():
        if "theme" in name and name.endswith(".xml"):
            root = parse_xml(name, data)
            for elem in root.iter():
                if _local(elem.tag) in ("latin", "ea", "cs"):
                    tf = elem.attrib.get("typeface")
                    if tf and not tf.startswith("+"):
                        fonts.add(tf)
    return fonts


def lint_package(parts: dict, allowed_fonts=None, profile: str = "pptx") -> list:
    """Return a list of violation dicts. Caller maps them to text/JSON."""
    violations = []

    def add(rule, severity, part, message):
        violations.append({"rule": rule, "severity": severity, "part": part, "message": message})

    # ---- PSL004 required parts
    for req in REQUIRED_PARTS_ANY:
        if req not in parts:
            add("PSL004", "error", req, "required package part is missing")
    if profile == "pptx":
        for req in REQUIRED_PARTS_PPTX:
            if req not in parts:
                add("PSL004", "error", req, "required pptx part is missing")

    xml_parts = {n: d for n, d in parts.items() if n.endswith(".xml") or n.endswith(".rels")}
    parsed = {}
    for name, data in xml_parts.items():
        try:
            parsed[name] = ET.fromstring(data)
        except ET.ParseError as exc:
            add("PSL004", "error", name, f"XML part fails to parse ({exc})")

    rels = collect_rels(parts)

    # ---- PSL003 dangling internal relationship targets
    for owner, mapping in sorted(rels.items()):
        for rid, target in sorted(mapping.items()):
            if target is not None and target not in parts:
                add("PSL003", "error", owner or "/",
                    f"relationship {rid} targets missing part {target}")

    # ---- PSL005 unresolved r:id / r:embed references
    for name, root in sorted(parsed.items()):
        if name.endswith(".rels"):
            continue
        owner_rels = rels.get(name, {})
        for elem in root.iter():
            for local, key, val in _attrs(elem):
                if key.startswith("{%s}" % REL_NS) and local in ("id", "embed", "link"):
                    if val not in owner_rels:
                        add("PSL005", "error", name,
                            f"attribute r:{local}='{val}' has no matching relationship")

    # ---- text rules over a:t / w:t elements
    allowed = set(allowed_fonts) if allowed_fonts is not None else None
    if allowed is None:
        allowed = theme_fonts(parts) or None  # rule disabled when no theme fonts found

    for name, root in sorted(parsed.items()):
        if name.endswith(".rels"):
            continue
        for elem in root.iter():
            tag = _local(elem.tag)
            if tag in ("t",):  # a:t in pptx, w:t in docx, t in xlsx
                text = (elem.text or "")
                low = text.lower()
                if any(p in low for p in PLACEHOLDER_PATTERNS):
                    add("PSL001", "error", name,
                        f"placeholder residue text: {text.strip()[:60]!r}")
                if TODO_RE.search(text):
                    add("PSL006", "warn", name,
                        f"todo/lorem residue text: {text.strip()[:60]!r}")
                if text.strip() == "" and text != "":
                    add("PSL007", "warn", name, "empty text run (whitespace-only)")
            elif tag in ("latin", "ea", "cs") and allowed is not None:
                if "theme" in name:
                    continue  # the theme *defines* the baseline; never flag it
                tf = elem.attrib.get("typeface")
                if tf and not tf.startswith("+") and tf not in allowed:
                    add("PSL002", "warn", name,
                        f"font {tf!r} not in allowlist {sorted(allowed)}")

    return violations


def lint_file(path, allowed_fonts=None, profile: str = "pptx"):
    parts = load_package(path)
    return lint_package(parts, allowed_fonts=allowed_fonts, profile=profile)


def exit_code_for(violations, strict: bool = False) -> int:
    if any(v["severity"] == "error" for v in violations):
        return 1
    if strict and violations:
        return 1
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="pptx-schema-lint",
        description="Structural lint for OOXML packages: placeholder residue, "
                    "font consistency, dangling relationships, editability.")
    ap.add_argument("file", help="path to .pptx/.docx/.xlsx package")
    ap.add_argument("--profile", choices=("pptx", "generic"), default="pptx",
                    help="pptx enforces presentation.xml; generic is package-agnostic")
    ap.add_argument("--allowed-fonts", default="",
                    help="comma-separated extra font names beyond theme fonts")
    ap.add_argument("--strict", action="store_true", help="warnings also fail (exit 1)")
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    args = ap.parse_args(argv)

    extra = [f.strip() for f in args.allowed_fonts.split(",") if f.strip()]
    try:
        violations = lint_file(args.file, allowed_fonts=extra or None, profile=args.profile)
    except LintError as exc:
        if args.json:
            print(json.dumps({"status": "error", "problems": [str(exc)]}, indent=2))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"status": "ok", "violations": violations}, indent=2))
    else:
        if not violations:
            print("pptx-schema-lint: clean")
        for v in violations:
            print(f"{v['rule']} [{v['severity']}] {v['part']}: {v['message']}")
        errors = sum(1 for v in violations if v["severity"] == "error")
        warns = len(violations) - errors
        print(f"{len(violations)} violation(s): {errors} error(s), {warns} warning(s)")
    return exit_code_for(violations, strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())
