#!/usr/bin/env python3
"""self_test battery for pptx-schema-lint (functional / error paths / edges).

Fixtures are minimal OOXML packages built in-memory with zipfile.
Run:  python self_test.py -v
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pptx_schema_lint as psl  # noqa: E402

HERE = Path(__file__).parent
PY = sys.executable or "python"

NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"

CONTENT_TYPES = """<?xml version="1.0"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
</Types>"""

ROOT_RELS = f"""<?xml version="1.0"?>
<Relationships xmlns="{NS_REL}">
<Relationship Id="rId1" Type="http://t/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>"""

PRES = f"""<?xml version="1.0"?>
<p:presentation xmlns:p="{NS_P}" xmlns:r="{NS_R}">
<p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
</p:presentation>"""

PRES_RELS = f"""<?xml version="1.0"?>
<Relationships xmlns="{NS_REL}">
<Relationship Id="rId1" Type="http://t/slide" Target="slides/slide1.xml"/>
</Relationships>"""

THEME = f"""<?xml version="1.0"?>
<a:theme xmlns:a="{NS_A}" name="T">
<a:themeElements>
<a:fontScheme name="T">
<a:majorFont><a:latin typeface="Cascadia Code"/></a:majorFont>
<a:minorFont><a:latin typeface="Cascadia Code"/></a:minorFont>
</a:fontScheme>
</a:themeElements>
</a:theme>"""


def slide_xml(texts, font=None):
    runs = ""
    for t in texts:
        if font:
            runs += f'<a:r><a:rPr><a:latin typeface="{font}"/></a:rPr><a:t>{t}</a:t></a:r>'
        else:
            runs += f"<a:r><a:t>{t}</a:t></a:r>"
    return f"""<?xml version="1.0"?>
<p:sld xmlns:p="{NS_P}" xmlns:a="{NS_A}" xmlns:r="{NS_R}">
<p:cSld><p:spTree><p:sp>
<p:txBody><a:p>{runs}</a:p></p:txBody>
</p:sp></p:spTree></p:cSld></p:sld>"""


SLIDE_RELS = f"""<?xml version="1.0"?>
<Relationships xmlns="{NS_REL}">
<Relationship Id="rId1" Type="http://t/image" Target="../media/image1.png"/>
<Relationship Id="rId2" Type="http://t/chart" Target="../charts/chart1.xml"/>
</Relationships>"""


def build_pptx(parts: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in parts.items():
            zf.writestr(name, data)
    return buf.getvalue()


def base_parts(slide_texts=("Hello world",), slide_font=None, extra=None,
               include_image=True, include_chart=True):
    parts = {
        "[Content_Types].xml": CONTENT_TYPES,
        "_rels/.rels": ROOT_RELS,
        "ppt/presentation.xml": PRES,
        "ppt/_rels/presentation.xml.rels": PRES_RELS,
        "ppt/theme/theme1.xml": THEME,
        "ppt/slides/slide1.xml": slide_xml(slide_texts, font=slide_font),
        "ppt/slides/_rels/slide1.xml.rels": SLIDE_RELS,
    }
    if include_image:
        parts["ppt/media/image1.png"] = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
    if include_chart:
        parts["ppt/charts/chart1.xml"] = f'<?xml version="1.0"?><c:chart xmlns:c="urn:x"/>';
    parts.update(extra or {})
    return parts


class TempCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def write_pkg(self, parts, name="pkg.pptx") -> Path:
        p = self.d / name
        p.write_bytes(build_pptx(parts))
        return p


# ------------------------------------------------------------- functional

class Functional(TempCase):
    def test_clean_package_zero_violations(self):
        p = self.write_pkg(base_parts())
        v = psl.lint_file(p)
        self.assertEqual(v, [])

    def test_placeholder_residue_detected(self):
        p = self.write_pkg(base_parts(slide_texts=("Click to add title",)))
        rules = {x["rule"] for x in psl.lint_file(p)}
        self.assertIn("PSL001", rules)

    def test_font_inconsistency_detected(self):
        p = self.write_pkg(base_parts(slide_font="Comic Sans MS"))
        vs = psl.lint_file(p)
        p2 = [x for x in vs if x["rule"] == "PSL002"]
        self.assertTrue(p2 and "Comic Sans MS" in p2[0]["message"])

    def test_dangling_relationship_detected(self):
        p = self.write_pkg(base_parts(include_chart=False))  # rel targets ../charts/chart1.xml
        rules = {x["rule"]: x for x in psl.lint_file(p)}
        self.assertIn("PSL003", rules)
        self.assertIn("chart1.xml", rules["PSL003"]["message"])

    def test_unresolved_rid_detected(self):
        pres = PRES.replace('r:id="rId1"', 'r:id="rId9"')
        p = self.write_pkg(base_parts(extra={"ppt/presentation.xml": pres}))
        rules = {x["rule"] for x in psl.lint_file(p)}
        self.assertIn("PSL005", rules)

    def test_todo_residue_warn_severity(self):
        p = self.write_pkg(base_parts(slide_texts=("TODO: fix layout",)))
        vs = psl.lint_file(p)
        self.assertTrue(any(x["rule"] == "PSL006" and x["severity"] == "warn" for x in vs))
        self.assertEqual(psl.exit_code_for(vs), 0)       # warns do not fail
        self.assertEqual(psl.exit_code_for(vs, strict=True), 1)

    def test_cli_exit_codes(self):
        clean = self.write_pkg(base_parts(), "clean.pptx")
        dirty = self.write_pkg(base_parts(slide_texts=("Click to add title",)), "dirty.pptx")
        r0 = subprocess.run([PY, str(HERE / "pptx_schema_lint.py"), str(clean)],
                            capture_output=True, text=True)
        self.assertEqual(r0.returncode, 0, r0.stdout + r0.stderr)
        r1 = subprocess.run([PY, str(HERE / "pptx_schema_lint.py"), str(dirty)],
                            capture_output=True, text=True)
        self.assertEqual(r1.returncode, 1)
        self.assertIn("PSL001", r1.stdout)
        rj = subprocess.run([PY, str(HERE / "pptx_schema_lint.py"), str(dirty), "--json"],
                            capture_output=True, text=True)
        payload = json.loads(rj.stdout)
        self.assertTrue(any(v["rule"] == "PSL001" for v in payload["violations"]))

    def test_generic_profile_skips_pptx_requirement(self):
        empty_rels = f'<?xml version="1.0"?><Relationships xmlns="{NS_REL}"/>'
        parts = {"[Content_Types].xml": CONTENT_TYPES, "_rels/.rels": empty_rels}
        p = self.write_pkg(parts, "minimal.oxml")
        v = psl.lint_file(p, profile="generic")
        self.assertEqual(v, [])
        v2 = psl.lint_file(p, profile="pptx")
        self.assertTrue(any(x["rule"] == "PSL004" for x in v2))


# ------------------------------------------------------------ error paths

class ErrorPaths(TempCase):
    def test_corrupt_zip_is_error(self):
        p = self.d / "corrupt.pptx"
        p.write_bytes(b"PK\x03\x04" + b"garbage" * 20)
        with self.assertRaises(psl.LintError):
            psl.lint_file(p)

    def test_empty_file_is_error(self):
        p = self.d / "empty.pptx"
        p.write_bytes(b"")
        with self.assertRaises(psl.LintError):
            psl.lint_file(p)

    def test_missing_file_is_error(self):
        with self.assertRaises(psl.LintError):
            psl.lint_file(self.d / "nope.pptx")

    def test_bad_xml_part_is_error(self):
        p = self.write_pkg(base_parts(extra={"ppt/slides/slide2.xml": b"<unclosed>"}))
        vs = psl.lint_file(p)
        self.assertTrue(any(x["rule"] == "PSL004" and "slide2.xml" in x["part"] for x in vs))

    def test_cli_error_exit_2(self):
        p = self.d / "corrupt.pptx"
        p.write_bytes(b"not a zip at all")
        r = subprocess.run([PY, str(HERE / "pptx_schema_lint.py"), str(p)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("error", r.stderr)


# ----------------------------------------------------------- extreme edges

class ExtremeEdges(TempCase):
    def test_empty_zip_reports_missing_parts(self):
        p = self.d / "emptyzip.pptx"
        p.write_bytes(build_pptx({}))
        vs = psl.lint_file(p)
        self.assertTrue(any(x["rule"] == "PSL004" for x in vs))

    def test_deeply_nested_xml_ok(self):
        depth = 500
        inner = "Click nowhere special"
        xml = "<a:p xmlns:a=\"%s\">" % NS_A + "<a:pPr>" * depth + "</a:pPr>" * depth \
            + f"<a:r><a:t>{inner}</a:t></a:r></a:p>"
        p = self.write_pkg(base_parts(extra={"ppt/slides/deep.xml": xml}))
        self.assertEqual(psl.lint_file(p), [])  # parses fine, no text flags

    def test_unicode_and_whitespace_runs(self):
        p = self.write_pkg(base_parts(slide_texts=("  ", "中文标题 ✓")))
        vs = psl.lint_file(p)
        self.assertTrue(any(x["rule"] == "PSL007" for x in vs))

    def test_text_is_not_over_flagged(self):
        p = self.write_pkg(base_parts(slide_texts=("Clickable demo link", "Todolist app")))
        vs = psl.lint_file(p)
        self.assertEqual([x for x in vs if x["rule"] in ("PSL001", "PSL006")], [])

    def test_large_package_perf(self):
        parts = base_parts()
        for i in range(50):
            parts[f"ppt/slides/s{i}.xml"] = slide_xml((f"Slide {i} body",))
        p = self.write_pkg(parts, "big.pptx")
        vs = psl.lint_file(p)
        self.assertEqual(vs, [])

    def test_rel_target_absolute_and_parent_paths(self):
        rels = f"""<?xml version="1.0"?>
<Relationships xmlns="{NS_REL}">
<Relationship Id="rId1" Type="http://t/x" Target="/ppt/media/image1.png"/>
</Relationships>"""
        parts = base_parts(extra={"ppt/slides/_rels/slide1.xml.rels": rels},
                           include_chart=True)
        p = self.write_pkg(parts, "abs.pptx")
        self.assertEqual([x for x in psl.lint_file(p) if x["rule"] == "PSL003"], [])


# ------------------------------------------------------- round-2 additions

class RoundTwo(TempCase):
    def test_duplicate_part_name_is_error(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, data in base_parts().items():
                zf.writestr(name, data)
            zf.writestr("ppt/slides/slide1.xml", slide_xml(("shadow copy",)))
        p = self.d / "dupe.pptx"
        p.write_bytes(buf.getvalue())
        with self.assertRaises(psl.LintError) as cm:
            psl.lint_file(p)
        self.assertIn("duplicate part", str(cm.exception))

    def test_allowed_fonts_override_theme(self):
        p = self.write_pkg(base_parts(slide_font="Brand Sans"))
        vs_default = psl.lint_file(p)  # theme says Cascadia Code -> PSL002
        self.assertTrue(any(x["rule"] == "PSL002" for x in vs_default))
        vs_allowed = psl.lint_file(p, allowed_fonts=["Brand Sans"])
        self.assertEqual([x for x in vs_allowed if x["rule"] == "PSL002"], [])

    def test_font_rule_disabled_without_theme(self):
        parts = base_parts()
        parts.pop("ppt/theme/theme1.xml")
        parts["ppt/slides/slide1.xml"] = slide_xml(("hi",), font="Weird Font")
        p = self.write_pkg(parts)
        vs = psl.lint_file(p)
        self.assertEqual([x for x in vs if x["rule"] == "PSL002"], [])

    def test_cli_strict_fails_on_warnings(self):
        dirty = self.write_pkg(base_parts(slide_texts=("TODO: tighten copy",)), "t.pptx")
        r0 = subprocess.run([PY, str(HERE / "pptx_schema_lint.py"), str(dirty)],
                            capture_output=True, text=True)
        self.assertEqual(r0.returncode, 0)
        r1 = subprocess.run([PY, str(HERE / "pptx_schema_lint.py"), str(dirty), "--strict"],
                            capture_output=True, text=True)
        self.assertEqual(r1.returncode, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
