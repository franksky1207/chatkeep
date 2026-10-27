"""ChatKeep public ChatGPT share-page decoder (stage 1-1).

Reference format: React Router turbo-stream, including multiple enqueue chunks.
Public pages only. Never stores fetched conversations.
"""
import argparse
import json
import re
import urllib.request
import urllib.error
import socket
import time
import hashlib
import http.client
import ipaddress
import ssl
from datetime import datetime, timezone
from collections import Counter
from urllib.parse import urlsplit

URL_PATTERN = re.compile(r"/share/[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}")
CHUNK_PATTERN = re.compile(r"streamController\.enqueue\(\s*(\")")

class ExtractionError(ValueError):
    pass

def validate_url(url):
    if not isinstance(url, str) or not re.fullmatch(r"https://chatgpt\.com" + URL_PATTERN.pattern, url):
        raise ExtractionError("Only public https://chatgpt.com/share/<uuid> URLs are allowed")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "chatgpt.com"
            or parsed.query or parsed.fragment
            or not URL_PATTERN.fullmatch(parsed.path)):
        raise ExtractionError("Only public https://chatgpt.com/share/<uuid> URLs are allowed")
    return url


def public_connection(address, timeout=30, source_address=None):
    """Pin a validated public destination in direct mode, preventing DNS rebinding.

    Trusted operator-configured HTTPS proxies enforce their own destination policy;
    they must not be confused with a user-supplied redirect or destination.
    """
    host, port = address
    if host != 'chatgpt.com' or port != 443:
        raise ExtractionError('目的地主機不在允許清單。')
    started = time.monotonic()
    choices = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not choices or any(not ipaddress.ip_address(item[4][0]).is_global for item in choices):
        raise ExtractionError('分享網址解析至非公開網路，已阻止連線。')
    last_error = None
    for family, kind, proto, _, target in choices:
        connection = socket.socket(family, kind, proto)
        try:
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError('公開網路連線逾時')
            connection.settimeout(remaining)
            if source_address:
                connection.bind(source_address)
            connection.connect(target)  # Resolved numeric sockaddr; no second DNS lookup.
            return connection
        except OSError as exc:
            last_error = exc
            connection.close()
    raise last_error or ExtractionError('無法建立公開網路連線。')


class PublicHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = public_connection


class PublicHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, request):
        return self.do_open(PublicHTTPSConnection, request, context=ssl.create_default_context())


def fetch_html(url, timeout=30, max_bytes=20_000_000, on_progress=None):
    """Anonymous HTTPS only; no cookies, scripts, cross-origin or off-path redirects."""
    validate_url(url)
    class RedirectGuard(urllib.request.HTTPRedirectHandler):
        max_redirections = 3
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            validate_url(newurl)
            if time.monotonic() - start > timeout:
                raise ExtractionError('擷取逾時，已停止轉址。')
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 ChatKeep/0.2", "Accept": "text/html",
        "Accept-Encoding": "identity"})
    start = time.monotonic()
    try:
        opener = urllib.request.build_opener(RedirectGuard)
        if not urllib.request.getproxies().get('https'):
            opener.add_handler(PublicHTTPSHandler())
        with opener.open(request, timeout=timeout) as response:
            if response.headers.get_content_type() != "text/html":
                raise ExtractionError("分享網址未回傳 HTML 頁面")
            if response.headers.get("Content-Encoding", "identity") != "identity":
                raise ExtractionError("不支援的壓縮回應，請稍後重試")
            length = response.headers.get("Content-Length")
            length = int(length) if length is not None else None
            if length is not None and length < 0:
                raise ExtractionError("無效的下載大小")
            if length is not None and length > max_bytes:
                raise ExtractionError("HTML exceeds permitted size")
            chunks, total = [], 0
            while True:
                if time.monotonic() - start > timeout:
                    raise ExtractionError("擷取逾時，請稍後重試")
                chunk = response.read1(min(65536, max_bytes + 1 - total))
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ExtractionError("HTML exceeds permitted size")
                if length is not None and total > length:
                    raise ExtractionError("HTML 下載大小與宣告不符")
                chunks.append(chunk)
                if on_progress:
                    on_progress(total, length if length else None)
            if length is not None and total != length:
                raise ExtractionError("HTML 下載不完整")
        return b"".join(chunks).decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise ExtractionError("分享頁回應 HTTP %d；可能已失效或限制匿名存取" % exc.code) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise ExtractionError("擷取逾時，請稍後重試") from exc
    except (urllib.error.URLError, UnicodeError, ValueError, http.client.IncompleteRead) as exc:
        if isinstance(exc, ExtractionError):
            raise
        raise ExtractionError("無法取得有效分享頁；請檢查網路、連結及存取限制") from exc


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
    """Decode positional turbo-stream references and P/E deferred settlements.

    Tag payloads are *not* ordinary pool references. Unsupported types fail closed;
    never evaluate JavaScript or silently replace broken/cyclic references.
    """
    lines = stream.splitlines()
    try:
        flat = json.loads(lines[0])
    except (json.JSONDecodeError, IndexError) as exc:
        raise ExtractionError("Malformed or incomplete stream root") from exc
    settlements = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        match = re.fullmatch(r"([PE])(\d+):(.*)", line)
        if not match:
            raise ExtractionError("Unsupported deferred stream frame")
        key = int(match[2])
        if key in settlements:
            raise ExtractionError("Duplicate promise settlement")
        try:
            settlements[key] = (match[1], json.loads(match[3]))
        except json.JSONDecodeError as exc:
            raise ExtractionError("Malformed promise in stream") from exc
    # Frames append to the same positional pool; their refs are global, not local.
    if not isinstance(flat, list) or not flat:
        raise ExtractionError("Empty turbo-stream root")
    targets = {}
    for key, (state, payload) in settlements.items():
        if isinstance(payload, list) and payload:
            targets[key] = (state, len(flat))
            flat.extend(payload)
        elif type(payload) is int:
            targets[key] = (state, payload)
        else:
            raise ExtractionError("Invalid deferred payload")
    resolving_promises = set()
    def resolve(pool, depth=0):
        if not isinstance(pool, list) or not pool:
            raise ExtractionError("Empty turbo-stream root")
        memo, active = {}, set()
        def edge(ref, level=0):
            if depth + level > 250:
                raise ExtractionError("Stream nesting too deep")
            if type(ref) is not int:
                raise ExtractionError("Invalid stream reference")
            if ref < 0:
                if ref in (-1, -7):  # undefined / array hole
                    return None
                if ref in (-2, -3, -6):
                    raise ExtractionError("Non-finite stream value cannot be represented in JSON")
                if ref == -4:
                    return -0.0
                if ref == -5:
                    return None
                raise ExtractionError("Unknown stream sentinel")
            if ref >= len(pool):
                raise ExtractionError("Broken stream reference")
            if ref in active:
                raise ExtractionError("Cyclic stream reference cannot be represented in JSON")
            if ref in memo:
                return memo[ref]
            active.add(ref)
            raw = pool[ref]
            if isinstance(raw, dict):
                out = {}
                for key, value in raw.items():
                    decoded = edge(int(key[1:]), level + 1) if re.fullmatch(r"_\d+", key) else key
                    if not isinstance(decoded, str) or decoded in out:
                        raise ExtractionError("Invalid or duplicate stream object key")
                    out[decoded] = edge(value, level + 1)
            elif isinstance(raw, list):
                if raw and isinstance(raw[0], str):
                    tag = raw[0]
                    if tag == "P" and len(raw) == 2 and type(raw[1]) is int:
                        promise = raw[1]
                        if promise not in targets:
                            raise ExtractionError("Unresolved deferred data")
                        if promise in resolving_promises:
                            raise ExtractionError("Cyclic deferred data")
                        state, target = targets[promise]
                        if state == "E":
                            raise ExtractionError("Deferred data rejected")
                        resolving_promises.add(promise)
                        out = edge(target, level + 1)
                        resolving_promises.remove(promise)
                    elif tag == "D" and len(raw) == 2 and isinstance(raw[1], str):
                        out = raw[1]
                    elif tag == "Z" and len(raw) == 2:
                        out = edge(raw[1], level + 1)
                    else:
                        raise ExtractionError("Unsupported turbo-stream tag: %s" % tag[:20])
                else:
                    out = [edge(value, level + 1) for value in raw]
            else:
                out = raw
            active.remove(ref)
            memo[ref] = out
            return out
        return edge(0)
    try:
        return resolve(flat)
    except RecursionError as exc:
        raise ExtractionError("Stream nesting too deep") from exc


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
    return _content(content)[0]


def _branch(conversation):
    mapping = conversation.get("mapping")
    current = conversation.get("current_node")
    linear = conversation.get("linear_conversation")
    if isinstance(mapping, dict) and mapping:
        if current not in mapping:
            raise ExtractionError("Cannot determine the active conversation branch")
        path, seen = [], set()
        while current is not None:
            if current in seen:
                raise ExtractionError("Cycle in conversation branch")
            seen.add(current)
            node = mapping.get(current)
            if not isinstance(node, dict):
                raise ExtractionError("Broken conversation parent")
            if node.get("id", current) != current:
                raise ExtractionError("Conversation node ID mismatch")
            path.append(node)
            current = node.get("parent")
        nodes = list(reversed(path))
        if isinstance(linear, list) and linear:
            if [n.get("id") for n in nodes] != [n.get("id") for n in linear if isinstance(n, dict)]:
                raise ExtractionError("Active branch and linear conversation disagree")
        return nodes, len(mapping), "current_node_parent_chain"
    if isinstance(linear, list) and linear:
        return linear, len(linear), "linear_conversation_only"
    raise ExtractionError("Cannot determine the active conversation branch")


def _content(content):
    """Return exact textual parts plus locations of unsupported payloads."""
    if isinstance(content, str):
        return content, []
    if not isinstance(content, dict):
        return "", ["content"]
    if isinstance(content.get("text"), str):
        return content["text"], []
    parts = content.get("parts")
    if not isinstance(parts, list):
        return "", ["content"]
    texts, unsupported = [], []
    for i, part in enumerate(parts):
        if isinstance(part, str):
            texts.append(part)
        elif isinstance(part, dict) and isinstance(part.get("text"), str):
            texts.append(part["text"])
            if part.get("type", "text") != "text":
                unsupported.append("parts[%d]" % i)
        else:
            unsupported.append("parts[%d]" % i)
    return "\n".join(texts), unsupported


def normalize(conversation, source_url="", on_progress=None):
    nodes, total_nodes, branch_source = _branch(conversation)
    records, messages, issues = [], [], []
    categories, roles, text_roles = Counter(), Counter(), Counter()
    content_type_roles = {}
    seen_ids = set()
    if on_progress:
        on_progress(0, len(nodes))
    def advance(index):
        if on_progress and ((index + 1) % 25 == 0 or index == len(nodes) - 1):
            on_progress(index + 1, len(nodes))
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ExtractionError("Invalid conversation node")
        message = node.get("message") if "message" in node else (node if "content" in node or "text" in node else None)
        if message is None:
            categories["structural"] += 1
            records.append({"node_id": node.get("id"), "parent": node.get("parent"),
                            "category": "structural", "message": None})
            advance(index)
            continue
        if not isinstance(message, dict):
            raise ExtractionError("Invalid message object")
        author = message.get("author") or {}
        role = author.get("role", message.get("role", "unknown")) if isinstance(author, dict) else "unknown"
        content = message.get("content", message.get("text", ""))
        text, unsupported = _content(content)
        metadata = message.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ExtractionError("Invalid message metadata")
        content_type = content.get("content_type", "text") if isinstance(content, dict) else "text"
        hidden = metadata.get("is_visually_hidden_from_conversation") is True
        channel, recipient = message.get("channel"), message.get("recipient")
        if role in ("system", "developer"):
            category = "system"
        elif role == "tool":
            category = "tool"
        elif hidden:
            category = "hidden"
        elif content_type in ("reasoning_recap", "thoughts", "model_editable_context") or channel in ("analysis", "justify", "confidence"):
            category = "internal"
        elif role == "assistant" and recipient not in (None, "all"):
            category = "tool_call"
        elif role not in ("user", "assistant"):
            category = "unknown"
        elif unsupported or content_type not in ("text", "code"):
            category = "non_text"
        elif text.strip():
            category = "visible"
        else:
            category = "empty"
        mid = message.get("id") or node.get("id")
        if not mid or mid in seen_ids:
            issues.append({"node_index": index, "message_id": mid, "reason": "missing_or_duplicate_id"})
        seen_ids.add(mid)
        if category in ("visible", "non_text") and message.get("status", "finished_successfully") != "finished_successfully":
            issues.append({"node_index": index, "message_id": mid, "reason": "unfinished_message"})
        if category in ("non_text", "unknown"):
            issues.append({"node_index": index, "message_id": mid, "reason": "unsupported_content",
                           "locations": unsupported, "content_type": content_type})
        record = {"node_id": node.get("id"), "parent": node.get("parent"), "category": category,
                  "message": {"id": mid, "role": role, "create_time": message.get("create_time"),
                              "update_time": message.get("update_time"), "author": author,
                              "text": text, "content": content, "metadata": metadata,
                              "channel": channel, "recipient": recipient, "status": message.get("status"),
                              "content_type": content_type,
                              "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}}
        records.append(record)
        roles[role] += 1
        content_type_roles.setdefault(content_type, Counter())[role] += 1
        if text.strip():
            text_roles[role] += 1
        categories[category] += 1
        if category in ("visible", "non_text"):
            messages.append(dict(record["message"], category=category))
        advance(index)
    warnings = ["尚未完成逐訊息比對；擷取數量不代表內容已全部驗證。",
                "閱讀版會轉換支援的 Markdown／介面元件；未知格式保留原文，圖片不以替代圖冒充。"]
    if branch_source == "linear_conversation_only":
        warnings.append("來源僅有線性訊息；無法獨立核對目前分支。")
    if issues:
        warnings.append("有 %d 項缺漏或無法解析內容，請檢查完整性報告。" % len(issues))
    if not messages:
        raise ExtractionError("分享頁未包含可匯出的可見訊息")
    return {"schema_version": "1.0", "source_url": source_url,
            "title": conversation.get("title") or "未命名對話",
            "branch": {"source": branch_source, "current_node": conversation.get("current_node"),
                       "node_ids": [n.get("id") for n in nodes],
                       "off_branch_node_ids": sorted(set(conversation.get("mapping", {})) - {n.get("id") for n in nodes})},
            "records": records, "messages": messages,
            "report": {"raw_nodes": len(nodes), "raw_messages": sum(roles.values()),
                       "total_mapping_nodes": total_nodes, "off_branch_nodes": total_nodes - len(nodes),
                       "readable_messages": len(messages), "visible_text_messages": categories["visible"],
                       "roles": dict(roles), "text_roles": dict(text_roles),
                       "content_type_roles": {k: dict(v) for k, v in content_type_roles.items()},
                       "visible_roles": dict(Counter(m["role"] for m in messages)),
                       "categories": dict(categories), "issues": issues,
                       "warnings": warnings, "status": "partial" if issues else "extracted_unverified",
                       "verified_against_live_page": False, "reference_comparison": "not_performed"}}


def parse_html(html, url="", on_progress=None):
    try:
        result = normalize(find_conversation(hydrate(extract_stream(html))), url, on_progress=on_progress)
        # Guarantee the single public model is strict JSON, including raw content.
        json.dumps(result, ensure_ascii=False, allow_nan=False)
        return result
    except (RecursionError, TypeError, ValueError) as exc:
        if isinstance(exc, ExtractionError):
            raise
        raise ExtractionError("來源資料無法安全表示為標準 JSON") from exc


def extract_url(url, on_fetched=None, on_download_progress=None, on_parse_progress=None):
    html = fetch_html(url, on_progress=on_download_progress)
    if on_fetched:
        on_fetched()
    result = parse_html(html, url, on_progress=on_parse_progress)
    result["provenance"] = {"retrieved_at": datetime.now(timezone.utc).isoformat(),
                            "html_bytes": len(html.encode("utf-8")),
                            "html_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
                            "stream_chunks": len(list(CHUNK_PATTERN.finditer(html)))}
    return result

def main():
    parser = argparse.ArgumentParser(description="ChatKeep share parser (stage 1-1)")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url")
    source.add_argument("--html", help="Saved share-page HTML for offline verification")
    args = parser.parse_args()
    try:
        if args.url:
            result = extract_url(args.url)
        else:
            with open(args.html, encoding="utf-8") as fp:
                html = fp.read()
            result = parse_html(html)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ExtractionError, OSError) as exc:
        parser.exit(2, "ChatKeep extraction failed: %s\n" % exc)

if __name__ == "__main__":
    main()
