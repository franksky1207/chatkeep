"""Bounded official single-conversation adapter. No network or filesystem I/O."""
import json
import math
from collections import Counter
from chatkeep import normalize, ExtractionError
from word_export import _check_xml, ExportError

MAX_INPUT = 2_000_000
MAX_NODES = 5000
MAX_MESSAGES = 2000
MAX_TEXT = 1_000_000
MAX_MESSAGE = 100_000


class OfficialError(ValueError):
    def __init__(self, code, message, status=422):
        super().__init__(message)
        self.code, self.status = code, status


def fail(code='INVALID_CONVERSATION', message='官方對話結構不支援或損壞。', status=422):
    raise OfficialError(code, message, status)


def decode(body):
    if not 0 < len(body) <= MAX_INPUT:
        fail('INPUT_TOO_LARGE', '單一對話 JSON 超過 2 MB 上限。', 413)
    # Bound nesting before the standard decoder allocates recursive containers.
    depth, quoted, escaped = 0, False, False
    for c in body:
        if quoted:
            if escaped: escaped = False
            elif c == 92: escaped = True
            elif c == 34: quoted = False
        elif c == 34: quoted = True
        elif c in (123, 91):
            depth += 1
            if depth > 32: fail('STRUCTURE_LIMIT', 'JSON 巢狀深度超過 32 層。', 413)
        elif c in (125, 93): depth -= 1

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: fail('INVALID_JSON', 'JSON 含重複欄位。', 400)
            result[key] = value
        return result

    def constant(_):
        fail('INVALID_JSON', 'JSON 含非標準數值。', 400)

    try:
        value = json.loads(body.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, OfficialError): raise
        fail('INVALID_JSON', '請提供有效 UTF-8 JSON。', 400)
    stack, count = [value], 0
    while stack:
        item = stack.pop(); count += 1
        if count > 100000: fail('STRUCTURE_LIMIT', 'JSON 結構項目過多。', 413)
        if isinstance(item, dict): stack.extend(item.keys()); stack.extend(item.values())
        elif isinstance(item, list): stack.extend(item)
        elif isinstance(item, str):
            try: _check_xml(item)
            except ExportError: fail('INVALID_CHARACTERS', 'JSON 含 Word 無法保存的字元。')
        elif isinstance(item, float) and not math.isfinite(item):
            fail('INVALID_JSON', 'JSON 含非有限數值。', 400)
    return value


def normalize_official(body):
    conv = decode(body)
    if not isinstance(conv, dict) or 'conversations' in conv or 'linear_conversation' in conv:
        fail('SINGLE_CONVERSATION_REQUIRED', '只接受一個已選取的官方對話物件，不接受備份陣列或包裝。')
    mapping = conv.get('mapping')
    if not isinstance(mapping, dict) or not mapping: fail()
    if len(mapping) > MAX_NODES: fail('NODE_LIMIT', '原始節點超過 5,000。', 413)
    if not isinstance(conv.get('title'), str) or len(conv['title']) > 1000: fail()
    for field in ('id', 'conversation_id'):
        if conv.get(field) is not None and (not isinstance(conv[field], str) or len(conv[field]) > 256): fail()
    current = conv.get('current_node')
    if not isinstance(current, str) or current not in mapping:
        fail('INVALID_BRANCH', '缺少有效 current_node，無法安全決定目前分支。')
    for key, node in mapping.items():
        if not key or len(key) > 256 or not isinstance(node, dict): fail()
        if node.get('id', key) != key or 'parent' not in node: fail('INVALID_BRANCH')
        parent = node['parent']
        if parent is not None and (not isinstance(parent, str) or parent not in mapping): fail('INVALID_BRANCH')
        children = node.get('children', [])
        if not isinstance(children, list) or any(not isinstance(c, str) or c not in mapping for c in children): fail('INVALID_BRANCH')
        if len(children) != len(set(children)): fail('INVALID_BRANCH')
        for child in children:
            if not isinstance(mapping[child], dict) or mapping[child].get('parent') != key: fail('INVALID_BRANCH')
        if parent is not None:
            parent_node = mapping[parent]
            if isinstance(parent_node, dict) and 'children' in parent_node:
                if not isinstance(parent_node['children'], list) or key not in parent_node['children']: fail('INVALID_BRANCH')
    # Check all parent chains, including off-path cycles, in linear time.
    completed = set()
    for key in mapping:
        trail = set()
        while key is not None and key not in completed:
            if key in trail: fail('INVALID_BRANCH', '節點關係含循環。')
            trail.add(key); key = mapping[key]['parent']
        completed.update(trail)
    path, cursor = [], current
    while cursor is not None:
        path.append(cursor); cursor = mapping[cursor]['parent']
    ids = set()
    for key in path:
        msg = mapping[key].get('message')
        if msg is None: continue
        if not isinstance(msg, dict): fail()
        mid = msg.get('id', key)
        if not isinstance(mid, str) or not mid or len(mid) > 256: fail()
        if mid in ids: fail('DUPLICATE_MESSAGE', '有效路徑含重複訊息 ID，未輸出重複內容。')
        ids.add(mid)
        author = msg.get('author')
        if not isinstance(author, dict) or author.get('role') not in ('user', 'assistant', 'system', 'developer', 'tool'):
            fail('UNSUPPORTED_CONTENT', '有效路徑含未知訊息角色。')
        if not isinstance(msg.get('content'), (dict, str)): fail()
        if msg.get('metadata') is not None and not isinstance(msg['metadata'], dict): fail()
        metadata = msg.get('metadata') or {}
        if 'is_visually_hidden_from_conversation' in metadata and not isinstance(metadata['is_visually_hidden_from_conversation'], bool): fail()
        for field in ('channel', 'recipient', 'status'):
            if msg.get(field) is not None and not isinstance(msg[field], str): fail()
        content = msg['content']
        if isinstance(content, dict):
            content_type = content.get('content_type', 'text')
            if not isinstance(content_type, str): fail()
            visible = (author['role'] in ('user', 'assistant') and not metadata.get('is_visually_hidden_from_conversation')
                       and content_type not in ('reasoning_recap', 'thoughts', 'model_editable_context')
                       and msg.get('channel') not in ('analysis', 'justify', 'confidence')
                       and not (author['role'] == 'assistant' and msg.get('recipient') not in (None, 'all')))
            if visible:
                # Do not let the permissive share-page adapter silently prefer
                # content.text over a second, potentially non-text parts payload.
                parts = content.get('parts')
                text = content.get('text')
                supported = (content_type in ('text', 'code')
                             and not (set(content) - {'content_type', 'parts', 'text', 'language'})
                             and not ('text' in content and 'parts' in content)
                             and (isinstance(text, str) or isinstance(parts, list) and all(
                                 isinstance(p, str) or isinstance(p, dict) and isinstance(p.get('text'), str)
                                 and p.get('type', 'text') == 'text' and not (set(p) - {'type', 'text'}) for p in parts)))
                if not supported: fail('UNSUPPORTED_CONTENT', '有效對話含未支援或不明確的內容格式。')
    # Official nodes may omit redundant node.id; the shared parser needs it for reporting.
    adapted = dict(conv, mapping={k: dict(v, id=k) for k, v in mapping.items()})
    try: model = normalize(adapted)
    except (ExtractionError, TypeError, ValueError):
        fail('NO_EXPORTABLE_MESSAGES', '無法取得可匯出的有效對話訊息。')
    categories = Counter(r['category'] for r in model['records'])
    if categories['non_text'] or categories['unknown']:
        fail('UNSUPPORTED_CONTENT', '有效對話含未支援的非純文字內容；未產生可能缺漏的文件。')
    if any(i['reason'] == 'unfinished_message' for i in model['report']['issues']):
        fail('UNFINISHED_MESSAGE', '有效路徑含尚未完成的訊息。')
    messages = model['messages']
    if len(messages) > MAX_MESSAGES or sum(len(m['text']) for m in messages) > MAX_TEXT or any(len(m['text']) > MAX_MESSAGE for m in messages):
        fail('TEXT_LIMIT', '超過本端點 2,000 則、100 萬總字元或單則 10 萬字元限制。', 413)
    warnings = []
    def warn(code, count, text):
        if count: warnings.append({'code': code, 'count': count, 'message': text})
    warn('OFF_BRANCH_EXCLUDED', len(mapping)-len(path), '僅輸出 current_node 有效路徑，其他分支未輸出。')
    for category in ('structural', 'system', 'tool', 'hidden', 'internal', 'tool_call', 'empty'):
        warn('SKIPPED_' + category.upper(), categories[category], '已依規則略過 %s 節點。' % category)
    skipped = {k: v for k, v in categories.items() if k != 'visible'}
    report = {'source': 'official_json', 'raw_node_count': len(mapping), 'active_path_node_count': len(path),
              'active_path_message_count': len(ids), 'output_message_count': len(messages),
              'off_branch_node_count': len(mapping)-len(path), 'skipped_categories': skipped,
              'warnings': warnings, 'status': 'converted_with_warnings' if warnings else 'converted',
              'reference_comparison': 'not_performed', 'verified_against_live_page': False}
    model['report'] = {'warnings': ['%s（%d）' % (w['message'], w['count']) for w in warnings]}
    model['report']['warnings'].insert(0, '官方 JSON：原始節點 %d；有效路徑訊息 %d；輸出訊息 %d。' % (len(mapping), len(ids), len(messages)))
    return model, report
