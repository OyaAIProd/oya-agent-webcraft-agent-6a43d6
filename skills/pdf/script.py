"""PDF Processing — entry point dispatcher for sandbox execution."""
import json
import os
import re
import subprocess
import sys

_SKILL_DIR = os.path.dirname(__file__) if "__file__" in dir() else "/home/daytona/_skill"
SCRIPTS_DIR = os.path.join(_SKILL_DIR, "scripts")


def run_script(name, *args):
    """Run a script from the scripts/ directory."""
    path = os.path.join(SCRIPTS_DIR, name)
    if not os.path.exists(path):
        return {"error": f"Script not found: {name}"}
    result = subprocess.run(
        [sys.executable, path, *args],
        capture_output=True, text=True, timeout=120,
    )
    return {
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "exit_code": result.returncode,
    }


# ── Markdown text preprocessor ──

def _unwrap_text(raw: str) -> str:
    """Unwrap hard line breaks in body text while preserving markdown structure.

    Consecutive structural lines of the same type (table rows, list items)
    are kept together as one block separated by \\n (not \\n\\n).
    """
    _STRUCT = re.compile(r"^(?:#|[-*] |> |\||```|\d+\.\s)")
    _RULE = {"---", "***", "___", "----", "****"}

    def _line_type(s: str) -> str:
        if s.startswith("|"):
            return "table"
        if s.startswith("- ") or s.startswith("* "):
            return "bullet"
        if re.match(r"^\d+\.\s", s):
            return "number"
        if s.startswith("> "):
            return "quote"
        return ""

    lines = raw.split("\n")
    # First pass: unwrap body text, keep structural lines
    unwrapped: list[str] = []
    prev_structural = False
    for line in lines:
        s = line.strip()
        if not s:
            unwrapped.append("")
            continue
        is_struct = bool(_STRUCT.match(s)) or s in _RULE
        if is_struct or prev_structural:
            unwrapped.append(s)
            prev_structural = is_struct
        else:
            if unwrapped and unwrapped[-1] and not _STRUCT.match(unwrapped[-1]) and unwrapped[-1] not in _RULE:
                unwrapped[-1] += " " + s
            else:
                unwrapped.append(s)
            prev_structural = False

    # Second pass: group consecutive same-type structural lines into blocks
    blocks: list[str] = []
    i = 0
    while i < len(unwrapped):
        s = unwrapped[i].strip()
        if not s:
            if blocks and blocks[-1] != "":
                blocks.append("")
            i += 1
            continue
        lt = _line_type(s)
        if lt in ("table", "bullet", "number", "quote"):
            # Collect consecutive lines of same type (including separator rows for tables)
            group = [s]
            i += 1
            while i < len(unwrapped):
                ns = unwrapped[i].strip()
                if not ns:
                    break
                nlt = _line_type(ns)
                # Table separator rows (|---|---|) should stay with table
                is_table_sep = lt == "table" and re.match(r'^\|[\s\-:|]+\|$', ns)
                if nlt == lt or is_table_sep:
                    group.append(ns)
                    i += 1
                else:
                    break
            blocks.append("\n".join(group))
        else:
            blocks.append(s)
            i += 1

    return "\n\n".join(b for b in blocks if b is not None).strip()


# ── HTML helpers ──

def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _md_inline(t: str) -> str:
    """Convert **bold**, *italic*, `code`, [link](url) to HTML."""
    t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'\*(.+?)\*', r'<em>\1</em>', t)
    t = re.sub(r'`(.+?)`', r'<code>\1</code>', t)
    t = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', t)
    return t


# ── Markdown → HTML body ──

def _md_to_html(text: str) -> str:
    parts: list[str] = []
    in_code = False
    code_buf: list[str] = []

    for para in text.split("\n\n"):
        p = para.strip()
        if not p:
            continue
        # Code fences
        if in_code:
            if p.endswith("```"):
                code_buf.append(p[:-3].rstrip())
                parts.append(f'<pre>{_esc(chr(10).join(code_buf))}</pre>')
                code_buf, in_code = [], False
            else:
                code_buf.append(p)
            continue
        if p.startswith("```"):
            if p.endswith("```") and p.count("```") == 2:
                inner = p[3:]
                nl = inner.find("\n")
                if nl > 0 and inner[:nl].strip().isalpha():
                    inner = inner[nl + 1:]
                inner = inner.rstrip("`").strip()
                if inner:
                    parts.append(f'<pre>{_esc(inner)}</pre>')
            else:
                in_code = True
                rest = p[3:].strip()
                if rest and rest.split("\n", 1)[0].strip().isalpha():
                    rest = rest.split("\n", 1)[1] if "\n" in rest else ""
                if rest.strip():
                    code_buf.append(rest.strip())
            continue
        if p in ("---", "***", "___"):
            parts.append('<div style="page-break-after:always"></div>')
            continue
        if p in ("----", "****"):
            parts.append('<hr class="divider">')
            continue
        if p.startswith("### "):
            parts.append(f'<h3>{_md_inline(p[4:])}</h3>')
            continue
        if p.startswith("## "):
            parts.append(f'<h2>{_md_inline(p[3:])}</h2>')
            continue
        if p.startswith("# "):
            parts.append(f'<h1 class="doc-title">{_md_inline(p[2:])}</h1>')
            continue
        if p.startswith("> "):
            qt = p[2:].replace("\n> ", "<br>").replace("\n>", "<br>")
            parts.append(f'<blockquote><p>{_md_inline(qt)}</p></blockquote>')
            continue
        lines = p.split("\n")
        if re.match(r'^\d+\.\s', lines[0].strip()):
            items = ""
            for ln in lines:
                m = re.match(r'^\d+\.\s+(.*)', ln.strip())
                if m:
                    items += f'<li>{_md_inline(m.group(1))}</li>'
            parts.append(f'<ol>{items}</ol>')
            continue
        if lines[0].strip()[:2] in ("- ", "* "):
            items = "".join(f'<li>{_md_inline(ln.strip()[2:])}</li>' for ln in lines if ln.strip()[:2] in ("- ", "* "))
            parts.append(f'<ul>{items}</ul>')
            continue
        if "|" in p and p.lstrip().startswith("|"):
            parts.append(_md_table_to_html(p))
            continue
        parts.append(f'<p>{_md_inline(p.replace(chr(10), "<br>"))}</p>')
    return "\n".join(parts)


def _md_table_to_html(block: str) -> str:
    rows = [r.strip() for r in block.split("\n")
            if r.strip() and not re.match(r'^\|[\s\-:|]+\|$', r.strip())]
    if not rows:
        return ""
    html = '<table><thead><tr>'
    for c in [c.strip() for c in rows[0].strip("|").split("|")]:
        html += f'<th>{_md_inline(c)}</th>'
    html += '</tr></thead><tbody>'
    for row in rows[1:]:
        cells = [c.strip() for c in row.strip("|").split("|")]
        html += '<tr>' + "".join(f'<td>{_md_inline(c)}</td>' for c in cells) + '</tr>'
    html += '</tbody></table>'
    return html


# ── create_pdf: HTML → PDF via xhtml2pdf ──

def _create_pdf(inp: dict) -> dict:
    """Generate a styled HTML file, then convert to PDF.

    Uses xhtml2pdf if available (pure-Python HTML→PDF).
    Falls back to saving HTML as the output (the agent can serve it directly).
    """
    out = inp.get("output_path") or "output.pdf"
    title = inp.get("title", "")
    subtitle = inp.get("subtitle", "")
    author = inp.get("author", "")
    date_str = inp.get("date", "")
    raw_text = inp.get("text", "")
    text = _unwrap_text(raw_text)

    theme_raw = inp.get("theme", "")
    theme = json.loads(theme_raw) if isinstance(theme_raw, str) and theme_raw else (theme_raw or {})

    primary = theme.get("primary_color", theme.get("title_color", "#0f172a"))
    body_clr = theme.get("body_color", "#334155")
    muted_clr = theme.get("muted_color", "#94a3b8")
    accent = theme.get("accent_color", theme.get("line_color", "#6366f1"))
    heading_clr = theme.get("heading_color", theme.get("title_color", "#0f172a"))
    code_bg = theme.get("code_bg", "#f3f4f6")

    body_html = _md_to_html(text)

    title_html = ""
    if title:
        title_html += f'<div class="bar"></div><h1 class="title">{_md_inline(title)}</h1>'
    if subtitle:
        title_html += f'<p class="subtitle">{_md_inline(subtitle)}</p>'
    meta = " &middot; ".join(p for p in [author, date_str] if p)
    if meta:
        title_html += f'<p class="meta">{meta}</p>'
    if title:
        title_html += '<hr class="title-rule">'

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
@page {{ size: letter; margin: 0.8in;
  @bottom-right {{ content: "Page " counter(page); font-family: Helvetica, Arial, sans-serif; font-size: 8pt; color: {muted_clr}; }}
}}
body {{ font-family: Helvetica, Arial, sans-serif; font-size: 10.5pt; line-height: 1.65; color: {body_clr}; margin: 0; }}
.bar {{ width: 50px; height: 4px; background: {accent}; border-radius: 2px; margin-bottom: 10px; }}
.title {{ font-size: 26pt; font-weight: 700; color: {primary}; line-height: 1.15; margin: 0 0 6px 0; }}
.subtitle {{ font-size: 12.5pt; color: {muted_clr}; margin: 0 0 2px 0; }}
.meta {{ font-size: 9pt; color: {muted_clr}; margin: 6px 0 0 0; }}
hr.title-rule {{ border: none; border-top: 0.5pt solid {muted_clr}; margin: 14px 0 20px 0; }}
hr.divider {{ border: none; border-top: 0.5pt solid #d1d5db; margin: 16px 0; }}
h2 {{ font-size: 16pt; font-weight: 700; color: {heading_clr}; margin: 26px 0 8px 0; padding-left: 12px; border-left: 3px solid {accent}; }}
h3 {{ font-size: 12.5pt; font-weight: 700; color: {heading_clr}; margin: 20px 0 4px 0; }}
p {{ margin: 0 0 8px 0; }}
strong {{ color: {primary}; }}
code {{ font-family: Courier, monospace; font-size: 9pt; color: #c7254e; background: {code_bg}; padding: 1px 3px; }}
pre {{ font-family: Courier, monospace; font-size: 9pt; line-height: 1.5; background: {code_bg}; border: 0.5pt solid #e5e7eb; padding: 10px 12px; margin: 6px 0 10px 0; white-space: pre-wrap; word-wrap: break-word; }}
blockquote {{ margin: 6px 0; padding: 0 0 0 14px; border-left: 3px solid {accent}; color: {muted_clr}; font-style: italic; }}
blockquote p {{ margin: 0; }}
ul, ol {{ margin: 4px 0 10px 0; padding-left: 22px; }}
li {{ margin-bottom: 3px; }}
a {{ color: {accent}; text-decoration: none; }}
table {{ width: 100%; border-collapse: collapse; margin: 14px 0; font-size: 10pt; }}
thead th {{ background: {primary}; color: #fff; font-weight: 600; text-align: left; padding: 9px 12px; font-size: 9.5pt; }}
tbody td {{ padding: 8px 12px; border-bottom: 1px solid #e5e7eb; vertical-align: middle; }}
tbody td:first-child {{ font-weight: 600; }}
</style></head><body>
{title_html}
{body_html}
</body></html>"""

    # Save HTML to temp file
    html_path = out.replace(".pdf", ".html") if out.endswith(".pdf") else out + ".html"
    with open(html_path, "w") as f:
        f.write(html)

    # Convert HTML → PDF using pre-built html2pdf.mjs script with headless browser
    pdf_out = out if out.endswith(".pdf") else out + ".pdf"
    convert_js = os.path.join(SCRIPTS_DIR, "html2pdf.mjs")
    abs_html = os.path.abspath(html_path)
    abs_pdf = os.path.abspath(pdf_out)
    work_dir = os.path.dirname(abs_html)

    # Install browser package if needed, then convert
    install = subprocess.run(["bun", "add", "puppeteer"], capture_output=True, text=True, timeout=120, cwd=work_dir)
    if install.returncode != 0:
        print(f"A2ABASEAI_FILE: {os.path.abspath(html_path)}")
        return {"output": html_path, "title": title, "format": "html"}

    result = subprocess.run(["bun", "run", convert_js, abs_html, abs_pdf],
                             capture_output=True, text=True, timeout=60, cwd=work_dir)

    if result.returncode == 0 and os.path.exists(abs_pdf):
        os.unlink(html_path)
        print(f"A2ABASEAI_FILE: {abs_pdf}")
        return {"output": pdf_out, "title": title, "format": "pdf"}

    # Fallback: serve the HTML
    print(f"A2ABASEAI_FILE: {os.path.abspath(html_path)}")
    return {"output": html_path, "title": title, "format": "html",
            "note": f"PDF conversion failed: {(result.stderr or result.stdout or '').strip()[-200:]}"}


# ── Main dispatcher ──

try:
    inp = json.loads(os.environ.get("INPUT_JSON", "{}"))
    action = inp.get("action", "")
    file_path = inp.get("file_path", "")
    output_path = inp.get("output_path", "")

    if action == "extract_text":
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            pages_text = []
            for i, page in enumerate(pdf.pages):
                t = page.extract_text() or ""
                pages_text.append(f"--- Page {i+1} ---\n{t}")
        print(json.dumps({"text": "\n\n".join(pages_text), "pages": len(pdf.pages)}))

    elif action == "extract_tables":
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            all_tables = []
            for i, page in enumerate(pdf.pages):
                for j, table in enumerate(page.extract_tables()):
                    all_tables.append({"page": i + 1, "table_index": j, "rows": table})
        print(json.dumps({"tables": all_tables, "count": len(all_tables)}))

    elif action == "get_metadata":
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        meta = reader.metadata
        print(json.dumps({
            "pages": len(reader.pages),
            "title": meta.title if meta else None,
            "author": meta.author if meta else None,
            "subject": meta.subject if meta else None,
            "creator": meta.creator if meta else None,
        }))

    elif action == "merge_pdfs":
        from pypdf import PdfWriter, PdfReader
        files = [f.strip() for f in (inp.get("files", "") or file_path).split(",") if f.strip()]
        writer = PdfWriter()
        for f in files:
            for page in PdfReader(f).pages:
                writer.add_page(page)
        out = output_path or "merged.pdf"
        with open(out, "wb") as fh:
            writer.write(fh)
        print(f"A2ABASEAI_FILE: {os.path.abspath(out)}")
        print(json.dumps({"output": out, "total_pages": len(writer.pages)}))

    elif action == "split_pdf":
        from pypdf import PdfReader, PdfWriter
        reader = PdfReader(file_path)
        outputs = []
        for i, page in enumerate(reader.pages):
            w = PdfWriter()
            w.add_page(page)
            out = output_path or f"page_{i+1}.pdf"
            with open(out, "wb") as fh:
                w.write(fh)
            outputs.append(out)
        print(json.dumps({"outputs": outputs, "pages": len(outputs)}))

    elif action == "rotate_pages":
        from pypdf import PdfReader, PdfWriter
        rotation = int(inp.get("rotation", 90))
        reader = PdfReader(file_path)
        writer = PdfWriter()
        for page in reader.pages:
            page.rotate(rotation)
            writer.add_page(page)
        out = output_path or "rotated.pdf"
        with open(out, "wb") as fh:
            writer.write(fh)
        print(f"A2ABASEAI_FILE: {os.path.abspath(out)}")
        print(json.dumps({"output": out, "rotation": rotation, "pages": len(writer.pages)}))

    elif action == "create_pdf":
        result = _create_pdf(inp)
        print(json.dumps(result))

    elif action == "check_form_fields":
        result = run_script("check_fillable_fields.py", file_path)
        if result["exit_code"] == 0:
            print(json.dumps({"fillable": "fillable" in result["stdout"].lower(), "details": result["stdout"]}))
        else:
            print(json.dumps({"error": result["stderr"] or result["stdout"]}))

    elif action == "fill_form":
        field_values = inp.get("field_values", "{}")
        if isinstance(field_values, str):
            field_values = json.loads(field_values)
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([{"field_id": k, "value": v} for k, v in field_values.items()], f)
            values_path = f.name
        out = output_path or "filled.pdf"
        result = run_script("fill_fillable_fields.py", file_path, values_path, out)
        os.unlink(values_path)
        if result["exit_code"] == 0:
            print(f"A2ABASEAI_FILE: {os.path.abspath(out)}")
            print(json.dumps({"output": out, "fields_filled": len(field_values)}))
        else:
            print(json.dumps({"error": result["stderr"] or result["stdout"]}))

    elif action == "add_watermark":
        from pypdf import PdfReader, PdfWriter
        from pypdf.annotations import FreeText
        import io
        watermark_text = inp.get("text", "WATERMARK")
        reader = PdfReader(file_path)
        writer = PdfWriter()
        # Create watermark as a minimal PDF page using raw PDF content stream
        wm_pdf_bytes = (
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
            b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
            b"4 0 obj<</Length %(len)d>>stream\n%(stream)s\nendstream\nendobj\n"
            b"xref\n0 6\n0000000000 65535 f \ntrailer<</Size 6/Root 1 0 R>>\nstartxref\n0\n%%%%EOF"
        )
        # Build content stream: translate to center, rotate 45, draw text with transparency
        stream = (
            f"q\n"
            f"/GS1 gs\n"
            f"BT\n"
            f"/F1 50 Tf\n"
            f"0.7 0.7 0.7 rg\n"
            f"1 0 0.7071 0.7071 200 300 Tm\n"
            f"({watermark_text}) Tj\n"
            f"ET\n"
            f"Q"
        ).encode()
        # Simpler approach: use pypdf to stamp text via annotations or merge
        # Actually just build a watermark page with pypdf directly
        wm_writer = PdfWriter()
        wm_writer.add_blank_page(width=612, height=792)
        wm_page = wm_writer.pages[0]
        # pypdf can't draw text directly, so we'll use a content stream
        from pypdf.generic import (
            ArrayObject, DecodedStreamObject, DictionaryObject,
            NameObject, NumberObject, TextStringObject,
        )
        font_dict = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        resources = wm_page.get("/Resources", DictionaryObject())
        if not isinstance(resources, DictionaryObject):
            resources = DictionaryObject()
        font_res = resources.get("/Font", DictionaryObject())
        if not isinstance(font_res, DictionaryObject):
            font_res = DictionaryObject()
        font_res[NameObject("/F1")] = font_dict
        resources[NameObject("/Font")] = font_res
        wm_page[NameObject("/Resources")] = resources
        content = DecodedStreamObject()
        content.set_data(
            f"q 0.85 g BT /F1 48 Tf 0.7071 0.7071 -0.7071 0.7071 180 250 Tm ({watermark_text}) Tj ET Q".encode()
        )
        wm_page[NameObject("/Contents")] = content
        # Merge watermark onto each page
        for page in reader.pages:
            page.merge_page(wm_page)
            writer.add_page(page)
        out = output_path or "watermarked.pdf"
        with open(out, "wb") as fh:
            writer.write(fh)
        print(f"A2ABASEAI_FILE: {os.path.abspath(out)}")
        print(json.dumps({"output": out, "watermark": watermark_text, "pages": len(writer.pages)}))

    elif action == "extract_images":
        result = subprocess.run(
            ["pdfimages", "-j", file_path, output_path or "img"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            import glob
            images = glob.glob(f"{output_path or 'img'}*")
            print(json.dumps({"images": images, "count": len(images)}))
        else:
            print(json.dumps({"error": result.stderr or "pdfimages failed"}))

    elif action == "ocr":
        import pytesseract
        from pdf2image import convert_from_path
        images = convert_from_path(file_path)
        text = ""
        for i, image in enumerate(images):
            text += f"--- Page {i+1} ---\n"
            text += pytesseract.image_to_string(image)
            text += "\n\n"
        print(json.dumps({"text": text.strip(), "pages": len(images)}))

    else:
        print(json.dumps({"error": f"Unknown action: {action}. Available: extract_text, extract_tables, create_pdf, merge_pdfs, split_pdf, rotate_pages, fill_form, check_form_fields, add_watermark, extract_images, ocr, get_metadata"}))

except Exception as e:
    print(json.dumps({"error": str(e)}))
