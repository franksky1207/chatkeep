"""Shared input limits and measured Word structure budgets for both sources."""
from contextvars import ContextVar
from dataclasses import dataclass

MAX_MESSAGES = 5000
MAX_TEXT = 5_000_000
MAX_MESSAGE = 1_000_000
MAX_ARTIFACT = 16_000_000
MAX_VOLUMES = 16
DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


@dataclass(frozen=True)
class Capacity:
    elements: int = 120000
    xml_bytes: int = 8_000_000
    cells: int = 5000


CAPACITY = Capacity()
OBSERVER = ContextVar('word_structure_observer', default=None)


def observe(elements=0, cells=0):
    callback = OBSERVER.get()
    if callback: callback(elements, cells)


def guard_run(text):
    # These are actual Word break/tab/text nodes that add_run will allocate,
    # not a count of source Markdown or literal less-than characters.
    observe(2 + 2 * (text.count('\n') + text.count('\r') + text.count('\t')))


def supported_text_content(content):
    """Fail closed on ambiguous visible payloads, shared by the two modern adapters."""
    if isinstance(content, str): return True
    if not isinstance(content, dict): return False
    if content.get('content_type', 'text') not in ('text', 'code'): return False
    if set(content) - {'content_type', 'parts', 'text', 'language'}: return False
    if 'text' in content and 'parts' in content: return False
    if isinstance(content.get('text'), str): return True
    parts = content.get('parts')
    return isinstance(parts, list) and all(
        isinstance(p, str) or isinstance(p, dict) and isinstance(p.get('text'), str)
        and p.get('type', 'text') == 'text' and not (set(p) - {'type', 'text'}) for p in parts)
