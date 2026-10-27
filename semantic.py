"""Safe structural tokenizer for ChatGPT UI markup and Markdown.

Unrecognized components remain literal. No JavaScript evaluation.
"""
from dataclasses import dataclass, field
from html.parser import HTMLParser
from html import escape
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
            fence = marker.group().strip()
        elif fence is not None:
            code.append(line)
            if marker and marker.group().strip()[0] == fence[0] and len(marker.group().strip()) >= len(fence) and not line[marker.end():].strip():
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
        self.unsupported = False
        self.count = 0
    def raw(self, text):
        self.stack[-1].children.append(Node("text", text))
    def handle_starttag(self, tag, attrs):
        literal = self.get_starttag_text() or "<"+tag+">"
        self.count += 1
        if self.count > 20000 or len(self.stack) > 64:
            raise ValueError("UI complexity limit")
        if tag not in KNOWN and tag not in VOID:
            self.unsupported = True
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
        self.count += 1
        if self.count > 20000: raise ValueError('UI complexity limit')
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
    def handle_decl(self, data): self.raw("<!"+data+">")
    def handle_pi(self, data): self.raw("<?"+data+">")
    def unknown_decl(self, data): self.raw("<!["+data+"]>")

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
        original_part = part
        try:
            part, dynamic = static_attributes(part)
            if dynamic:
                warnings.append("動態介面僅還原可取得的靜態內容，不執行事件或版面運算；動態文字欄位保留原文。")
            cursor = 0
            for match in re.finditer(r"(`+)([^\n]*?)\1(?!`)", part):
                parser.feed(part[cursor:match.start()])
                parser.raw(match.group())  # Inline code cannot become UI markup.
                cursor = match.end()
            parser.feed(part[cursor:])
            parser.close()
            if len(parser.stack)!=1:
                raise ValueError("unbalanced UI")
            nodes.extend(parser.root.children)
            if parser.unsupported:
                warnings.append("未知介面元件保留原文，未執行其中程式。")
        except Exception:
            warnings.append("介面標記無法安全解析，保留原文")
            nodes.append(Node("markdown", original_part))
    return nodes, warnings

def flatten(node):
    if node.children: return "".join(flatten(child) for child in node.children)
    if node.kind in ("text", "markdown", "code", "asset") and node.text: return node.text
    if node.kind == "decor": return node.attrs.get("alt") or node.attrs.get("label") or node.attrs.get("title") or ""
    if not node.children:
        return node.attrs.get("label") or node.attrs.get("value") or node.attrs.get("placeholder") or node.attrs.get("text") or node.attrs.get("content") or ""
    return "".join(flatten(child) for child in node.children)


def static_attributes(source):
    """Lex JSX attributes on known tags without interpreting their expressions.

    Brace expressions can contain >, quotes and nested braces. Layout/handlers
    become inert empty attributes; text-bearing fields keep literal expressions.
    The normalized source is never changed, only this render-time token stream.
    """
    output, cursor, dynamic = [], 0, False
    start = re.compile(r'<(box|row|col|card|text|caption|bold|italic|button|badge|label|title|checkbox|radio|list|list-item|asyncimage|icon|divider|spacer)\b',re.I)
    inline = [(m.start(), m.end()) for m in re.finditer(r"(`+)([^\n]*?)\1(?!`)", source)]
    for match in start.finditer(source):
        if match.start() < cursor or any(left <= match.start() < right for left, right in inline): continue
        output.append(source[cursor:match.end()])
        i, quote = match.end(), None
        while i < len(source):
            char = source[i]
            if quote:
                output.append(char)
                if char == "\\" and i + 1 < len(source):
                    output.append(source[i+1]); i += 2; continue
                if char == quote: quote = None
                i += 1; continue
            if char in ('"', "'"):
                quote = char; output.append(char); i += 1; continue
            if char == '>':
                output.append(char); i += 1; break
            if char == '{':
                begin=i; depth=1; i+=1; inner_quote=None
                while i < len(source) and depth:
                    c=source[i]
                    if inner_quote:
                        if c=='\\': i+=2; continue
                        if c==inner_quote: inner_quote=None
                    elif c in ('"',"'",'`'): inner_quote=c
                    elif c=='{': depth+=1
                    elif c=='}': depth-=1
                    i+=1
                if depth: raise ValueError('Unclosed JSX attribute')
                expression=source[begin:i]
                attribute=re.search(r'([\w-]+)\s*=\s*$',source[match.end():begin])
                name=attribute.group(1).lower() if attribute else ''
                value=expression if name in {'label','value','placeholder','alt','query','title','text','content'} else ''
                output.append('"'+escape(value,quote=True)+'"' if attribute else ' ')
                dynamic=True
            else:
                output.append(char); i+=1
        cursor=i
    output.append(source[cursor:])
    return ''.join(output), dynamic
