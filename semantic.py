"""Safe structural tokenizer for ChatGPT UI markup and Markdown.

Unrecognized components remain literal. No JavaScript evaluation.
"""
from dataclasses import dataclass, field
from html.parser import HTMLParser
import re

KNOWN = {"box", "row", "col", "card", "text", "caption", "bold", "italic", "button", "badge", "label", "title", "checkbox", "radio", "list", "list-item"}
VOID = {"asyncimage", "icon", "divider", "spacer"}
FENCE = re.compile(r"^\s*(?:"+chr(96)+"{3,}|~{3,})")

@dataclass
class Node:
    kind: str
    text: str = ""
    children: list = field(default_factory=list)
    attrs: dict = field(default_factory=dict)

def chunks(source):
    parts, plain, code, fence = [], [], [], None
    for line in source.splitlines(keepends=True):
        marker = FENCE.match(line)
        if fence is None and marker:
            if plain:
                parts.append(("text", "".join(plain)))
                plain = []
            code = [line]
            fence = marker.group()[0] if marker.group()[0] in ("~", chr(96)) else marker.group().strip()[0]
        elif fence is not None:
            code.append(line)
            if marker and fence in marker.group():
                parts.append(("code", "".join(code)))
                code, fence = [], None
        else:
            plain.append(line)
    if code:
        parts.append(("code", "".join(code)))
    if plain:
        parts.append(("text", "".join(plain)))
    return parts

class UI(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.root = Node("root")
        self.stack = [self.root]
    def raw(self, text):
        self.stack[-1].children.append(Node("text", text))
    def handle_starttag(self, tag, attrs):
        literal = self.get_starttag_text() or "<"+tag+">"
        if tag in KNOWN:
            node = Node(tag, attrs=dict(attrs))
            self.stack[-1].children.append(node)
            self.stack.append(node)
        elif tag in VOID:
            self.stack[-1].children.append(Node("asset" if tag=="asyncimage" else "decor", literal, attrs=dict(attrs)))
        else:
            self.raw(literal)
    def handle_startendtag(self, tag, attrs):
        literal = self.get_starttag_text() or "<"+tag+"/>"
        if tag in KNOWN:
            self.stack[-1].children.append(Node(tag, attrs=dict(attrs)))
        elif tag in VOID:
            self.stack[-1].children.append(Node("asset" if tag=="asyncimage" else "decor", literal, attrs=dict(attrs)))
        else:
            self.raw(literal)
    def handle_endtag(self, tag):
        if tag in KNOWN and len(self.stack)>1 and self.stack[-1].kind==tag:
            self.stack.pop()
        else:
            self.raw("</"+tag+">")
    def handle_data(self, value): self.raw(value)
    def handle_entityref(self, name): self.raw("&"+name+";")
    def handle_charref(self, name): self.raw("&#"+name+";")
    def handle_comment(self, data): self.raw("<!--"+data+"-->")

def parse(source):
    """Returns (ordered nodes, warnings). Unknown/unbalanced input stays readable."""
    nodes, warnings = [], []
    for kind, part in chunks(source):
        if kind=="code":
            nodes.append(Node("code", part))
            continue
        if "<" not in part:
            nodes.append(Node("markdown", part))
            continue
        parser = UI()
        try:
            parser.feed(part)
            parser.close()
            if len(parser.stack)!=1:
                raise ValueError("unbalanced UI")
            nodes.extend(parser.root.children)
        except Exception:
            warnings.append("介面標記無法安全解析，保留原文")
            nodes.append(Node("markdown", part))
    return nodes, warnings

def flatten(node):
    if node.kind in ("text", "markdown", "code", "asset"): return node.text
    if node.kind == "decor": return ""
    if not node.children and node.kind in ("button", "badge", "label", "checkbox", "radio"):
        return node.attrs.get("label") or node.attrs.get("value") or node.attrs.get("placeholder") or ""
    return "".join(flatten(child) for child in node.children)
