"""Editable Word rendering for safe, static ChatGPT UI and Markdown.

No screenshots; all text is native Word runs or table cell content.
"""
import re
import textwrap
from docx.shared import Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from semantic import Node, parse, flatten

HEAD = re.compile(r"^(#{1,6})\s+(.+)$")
BULLET = re.compile(r"^(\s*)([-+*]|\d+[.)])\s+(.+)$")
BUBBLE = re.compile(r"^\s*(?:(LINE)\s*[｜|:]\s*)?([^：:\n]{1,20})[：:]\s*(.+)$")
CLOCK = re.compile(r"^\d{1,2}:\d{2}(?:\s|$)")
DIVIDER = re.compile(r"^\s*[-*_]{3,}\s*$")
CELL_LIMIT = 12

def shade(cell, fill="EDF4EF"):
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tcpr.append(shd)

def celltext(cell, value):
    cell.text = value
    for p in cell.paragraphs:
        p.paragraph_format.widow_control = True
        p.paragraph_format.space_after = Pt(1)

def box(document, text, fill="EFF4F2"):
    table = document.add_table(rows=1, cols=1)
    cell = table.cell(0, 0)
    shade(cell, fill)
    celltext(cell, text)
    return table

def bubble(document, speaker, content, timestamp=""):
    table = document.add_table(rows=1, cols=2)
    mine = speaker in ("我", "玩家", "使用者", "You")
    active = table.cell(0, 1 if mine else 0)
    shade(active, "E1F3DF" if mine else "F1F3F5")
    celltext(active, (speaker + (" · " + timestamp if timestamp else "") + "\n" + content))
    table.cell(0, 0 if mine else 1).text = ""

def markdown(document, value):
    lines = value.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if DIVIDER.match(line):
            document.add_paragraph("──────────")
            i += 1
            continue
        heading = HEAD.match(line)
        if heading:
            document.add_paragraph(heading.group(2), style="Heading %d" % min(len(heading.group(1))+2, 6))
            i += 1
            continue
        if line.startswith(">"):
            box(document, re.sub(r"^> ?", "", line), "F3F3F3")
            i += 1
            continue
        if line.count("|") >= 2 and i+1 < len(lines) and re.fullmatch(r"[\s|:\-]+", lines[i+1] or "") and "-" in lines[i+1]:
            rows = [line]
            i += 2
            while i < len(lines) and "|" in lines[i]:
                rows.append(lines[i])
                i += 1
            matrix = [split_cells(row) for row in rows]
            width = max(map(len, matrix))
            if width <= CELL_LIMIT:
                table = document.add_table(rows=len(matrix), cols=width)
                table.style = "Table Grid"
                for r, cols in enumerate(matrix):
                    for c, val in enumerate(cols):
                        celltext(table.cell(r,c), val)
                        if r == 0: shade(table.cell(r,c))
                table.rows[0]._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
            else:
                for row in rows: document.add_paragraph(row)
            continue
        bullet = BULLET.match(line)
        if bullet:
            numbered = bullet.group(2)[0].isdigit()
            try:
                paragraph = document.add_paragraph((bullet.group(2) + ' ' if numbered else '') + bullet.group(3), style="List Number" if numbered else "List Bullet")
                if numbered:
                    # Retain explicit source numbering (e.g. 5., 9.) rather than
                    # silently restarting a Word list at 1.
                    numpr = paragraph._p.get_or_add_pPr().get_or_add_numPr()
                    numpr.get_or_add_numId().val = 0
            except KeyError:
                document.add_paragraph(line)
            i += 1
            continue
        match = BUBBLE.match(line)
        if match and match.group(1):
            content = match.group(3)
            timestamp = ""
            clock = re.match(r"(\d{1,2}:\d{2})\s+(.+)", content)
            if clock:
                timestamp, content = clock.groups()
            bubble(document, match.group(2).strip(), content, timestamp)
            i += 1
            continue
        # Keep consecutive prose lines in one editable paragraph, preserving line breaks.
        group = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not (HEAD.match(lines[i]) or BULLET.match(lines[i]) or DIVIDER.match(lines[i]) or lines[i].startswith(">") or (lines[i].count("|") >= 2 and i+1 < len(lines) and re.fullmatch(r"[\s|:\-]+", lines[i+1] or "")) or (BUBBLE.match(lines[i]) and BUBBLE.match(lines[i]).group(1))):
            group.append(lines[i])
            i += 1
        document.add_paragraph("\n".join(group))

def render(document, node):
    kind = node.kind
    if kind == "markdown" or kind == "text" and not node.children:
        markdown(document, flatten(node))
    elif kind == "code":
        p = document.add_paragraph()
        p.style = document.styles["Normal"]
        p.paragraph_format.left_indent = Pt(12)
        p.paragraph_format.right_indent = Pt(8)
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(7)
        p.paragraph_format.widow_control = True
        run = p.add_run(node.text)
        run.font.name = "Consolas"
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(38, 59, 70)
    elif kind == "asset":
        attrs = node.attrs
        label = attrs.get("alt") or attrs.get("query") or "圖片原始資產未包含在分享資料"
        box(document, "[圖片未嵌入] " + label, "F5F4EC")
    elif kind == "decor":
        value = flatten(node)
        if value:
            document.add_paragraph(value)
        return
    elif kind in ("box", "card"):
        table = document.add_table(rows=1, cols=1)
        shade(table.cell(0, 0))
        label = node.attrs.get('label') or node.attrs.get('title')
        if label:
            table.cell(0, 0).add_paragraph(label)
        render_nodes(table.cell(0, 0), node.children)
        if not node.children and not label and flatten(node):
            table.cell(0, 0).add_paragraph(flatten(node))
    elif kind == "row":
        children = [c for c in node.children if flatten(c).strip()]
        if len(children) >= 2 and len(children) <= 4:
            table = document.add_table(rows=1, cols=len(children))
            table.style = "Table Grid"
            for i, child in enumerate(children):
                render_nodes(table.cell(0, i), child.children if child.kind == "col" else [child])
        else:
            # A one-column row is ordinary flow; wide rows fall back to ordered
            # blocks. Flattening here used JSX indentation as dozens of hard
            # breaks in one nested cell and could clip its final line in Writer.
            render_nodes(document, node.children)
    elif kind in ("col", "caption", "text", "bold", "italic"):
        value = flatten(node)
        # JSX indentation/blank source lines are layout syntax, not empty visual
        # text. Preserve meaningful line breaks and every non-whitespace character.
        value = '\n'.join(line.rstrip() for line in textwrap.dedent(value).splitlines() if line.strip())
        p = document.add_paragraph()
        r = p.add_run(value)
        if kind=="caption": r.font.size=Pt(9); r.font.color.rgb=RGBColor(100,110,110)
        if kind=="bold": r.bold=True
        if kind=="italic": r.italic=True
    else:
        markdown(document, flatten(node))

def render_message(document, value):
    nodes, warnings = parse(value)
    render_nodes(document, nodes)
    if any(node.kind == "asset" or node.kind in ("text", "markdown") and re.search(r"<AsyncImage\b", node.text, re.I) for node in walk(nodes)):
        warnings.append("[圖片未嵌入] 圖片原始資產未取得，已留下文字註記，未嵌入替代圖片。")
    if re.search(r"\$\$|\\\(|\\\[", value):
        warnings.append("數學公式保留可編輯原文，尚未轉成 Word 原生公式。")
    return warnings


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node.children)


def render_nodes(document, nodes):
    # HTMLParser may split ordinary prose into punctuation/entity callbacks.
    # Keep adjacent literals together rather than inventing a paragraph per token.
    pending = []
    def flush():
        if pending:
            markdown(document, "".join(pending))
            pending.clear()
    for node in nodes:
        if node.kind in ("text", "markdown") and not node.children and node.text:
            pending.append(node.text)
        else:
            flush()
            render(document, node)
    flush()
    if hasattr(document, '_tc'):
        initial = document._tc.find(qn('w:p'))
        if initial is not None and len(document._tc) > 2 and not ''.join(initial.itertext()).strip() and not list(initial.iter(qn('w:br'))):
            document._tc.remove(initial)


def split_cells(row):
    cells, current, code, escaped = [], [], False, False
    value = row.strip()
    if value.startswith('|'): value = value[1:]
    if value.endswith('|') and not value.endswith('\\|'): value = value[:-1]
    for char in value:
        if escaped:
            current.append(char if char == '|' else '\\' + char)
            escaped = False
        elif char == '\\': escaped = True
        elif char == '`':
            code = not code
            current.append(char)
        elif char == '|' and not code:
            cells.append(''.join(current).strip()); current = []
        else: current.append(char)
    if escaped: current.append('\\')
    cells.append(''.join(current).strip())
    return cells
