"""ChatKeep public ChatGPT share-page decoder (stage 1-1).

Reference format: React Router turbo-stream, including multiple enqueue chunks.
Public pages only. Never stores fetched conversations.
"""
import argparse
import json
import re
import urllib.request
from collections import Counter
from urllib.parse import urlsplit

URL_PATTERN = re.compile(r"/share/[a-fA-F0-9-]{36}")
CHUNK_PATTERN = re.compile(r"streamController\.enqueue\(\s*(\")")

class ExtractionError(ValueError):
    pass

def validate_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "chatgpt.com"
            or parsed.query or parsed.fragment
            or not URL_PATTERN.fullmatch(parsed.path)):
        raise ExtractionError("Only public https://chatgpt.com/share/<uuid> URLs are allowed")
    return url

def fetch_html(url, timeout=30, max_bytes=20_000_000):
    validate_url(url)
    class RedirectGuard(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if urlsplit(newurl).hostname != "chatgpt.com" or urlsplit(newurl).scheme != "https":
                raise ExtractionError("Cross-origin redirect blocked")
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ChatKeep/0.1", "Accept": "text/html"})
    with urllib.request.build_opener(RedirectGuard).open(request, timeout=timeout) as response:
        raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ExtractionError("HTML exceeds permitted size")
    return raw.decode("utf-8", errors="replace")

def extract_stream(html):
    pieces = []
    for match in CHUNK_PATTERN.finditer(html):
        start = match.end() - 1
        pos = start + 1
        escaped = False
        while pos < len(html):
            c = html[pos]
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                break
            pos += 1
        if pos == len(html):
            raise ExtractionError("Unterminated stream chunk")
        try:
            pieces.append(json.loads(html[start:pos + 1]))
        except json.JSONDecodeError as exc:
            raise ExtractionError("Malformed embedded stream chunk") from exc
    if not pieces:
        raise ExtractionError("No ChatGPT stream found")
    return "".join(pieces)

def hydrate(stream):
    lines = stream.split("\n")
    try:
        flat = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise ExtractionError("Malformed or incomplete stream root") from exc
    if not isinstance(flat, list) or not flat:
        raise ExtractionError("Empty turbo-stream root")
    promises = {}
    for line in lines[1:]:
        match = re.fullmatch(r"P(\d+):(.*)", line)
        if match:
            try:
                promises[int(match.group(1))] = json.loads(match.group(2))
            except json.JSONDecodeError as exc:
                raise ExtractionError("Malformed promise in stream") from exc
    def resolve(pool, deferred=None):
        memo = {}
        active = set()
        def edge(obj, depth=0):
            if depth > 300:
                raise ExtractionError("Stream nesting too deep")
            if type(obj) is not int:
                return obj
            if obj < 0:
                return None
            if deferred and obj in deferred:
                return resolve(deferred[obj])
            if obj >= len(pool):
                raise ExtractionError("Broken stream reference")
            if obj in memo:
                return memo[obj]
            if obj in active:
                return None
            active.add(obj)
            raw = pool[obj]
            if isinstance(raw, dict):
                out = {}
                memo[obj] = out
                for key, value in raw.items():
                    decoded_key = edge(int(key[1:]), depth + 1) if re.fullmatch(r"_\d+", key) else key
                    out[str(decoded_key)] = edge(value, depth + 1)
            elif isinstance(raw, list):
                out = []
                memo[obj] = out
                out.extend(edge(value, depth + 1) for value in raw)
            else:
                out = raw
            active.remove(obj)
            memo[obj] = out
            return out
        return edge(0)
    return resolve(flat, promises)

def find_conversation(tree):
    stack = [tree]
    seen = set()
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, dict):
            if isinstance(current.get("mapping"), dict) or isinstance(current.get("linear_conversation"), list):
                return current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    raise ExtractionError("Decoded stream contains no conversation object")

def content_to_text(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, dict):
        return ""
    if isinstance(content.get("text"), str):
        return content["text"]
    parts = content.get("parts")
    if not isinstance(parts, list):
        return ""
    out = []
    for part in parts:
        if isinstance(part, str):
            out.append(part)
        elif isinstance(part, dict):
            if isinstance(part.get("text"), str):
                out.append(part["text"])
            else:
                out.append("[unavailable asset: %s]" % (part.get("content_type") or part.get("type") or "unknown"))
    return "\n".join(out)

def normalize(conversation, source_url=""):
    nodes = conversation.get("linear_conversation")
    if not isinstance(nodes, list) or not nodes:
        mapping = conversation.get("mapping")
        node_id = conversation.get("current_node")
        if not isinstance(mapping, dict) or node_id not in mapping:
            raise ExtractionError("Cannot determine the active conversation branch")
        path = []
        visited = set()
        while node_id is not None:
            if node_id in visited:
                raise ExtractionError("Cycle in conversation branch")
            visited.add(node_id)
            node = mapping.get(node_id)
            if not isinstance(node, dict):
                raise ExtractionError("Broken conversation parent")
            path.append(node)
            node_id = node.get("parent")
        nodes = list(reversed(path))
    messages = []
    roles = Counter()
    skipped = 0
    for node in nodes:
        message = node.get("message") if isinstance(node, dict) and isinstance(node.get("message"), dict) else node
        if not isinstance(message, dict):
            skipped += 1
            continue
        author = message.get("author") or {}
        role = author.get("role", message.get("role", "unknown")) if isinstance(author, dict) else "unknown"
        text = content_to_text(message.get("content", message.get("text", "")))
        if not text.strip():
            skipped += 1
            continue
        roles[role] += 1
        messages.append({"id": message.get("id") or node.get("id"), "role": role,
                         "create_time": message.get("create_time"), "text": text})
    ids = [m["id"] for m in messages if m["id"]]
    warnings = []
    if skipped:
        warnings.append("%d empty/unreadable nodes excluded from visible list" % skipped)
    if len(ids) != len(set(ids)):
        warnings.append("Duplicate message IDs")
    return {"source_url": source_url, "title": conversation.get("title") or "Untitled",
            "messages": messages,
            "report": {"raw_nodes": len(nodes), "readable_messages": len(messages),
                       "roles": dict(roles), "empty_nodes": skipped,
                       "warnings": warnings, "verified_against_live_page": False}}

def parse_html(html, url=""):
    return normalize(find_conversation(hydrate(extract_stream(html))), url)

def main():
    parser = argparse.ArgumentParser(description="ChatKeep share parser (stage 1-1)")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url")
    source.add_argument("--html", help="Saved share-page HTML for offline verification")
    args = parser.parse_args()
    try:
        if args.url:
            html = fetch_html(args.url)
        else:
            with open(args.html, encoding="utf-8") as fp:
                html = fp.read()
        print(json.dumps(parse_html(html, args.url or ""), ensure_ascii=False, indent=2))
    except (ExtractionError, OSError) as exc:
        parser.exit(2, "ChatKeep extraction failed: %s\n" % exc)

if __name__ == "__main__":
    main()
