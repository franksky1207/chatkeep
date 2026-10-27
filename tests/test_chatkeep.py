"""Synthetic offline tests; no private conversation data in public repository."""
import json
import unittest
from chatkeep import parse_html, validate_url, ExtractionError

class Encoder:
    def __init__(self):
        self.flat = []
    def add(self, item):
        i = len(self.flat)
        self.flat.append(None)
        if isinstance(item, dict):
            out = {}
            for key, val in item.items():
                out["_" + str(self.add(key))] = self.add(val)
            self.flat[i] = out
        elif isinstance(item, list):
            self.flat[i] = [self.add(v) for v in item]
        else:
            self.flat[i] = item
        return i

class TestParser(unittest.TestCase):
    def test_url_guard(self):
        url = "https://chatgpt.com/share/6acdedca-cfa0-83ec-9622-dba167dfee84"
        self.assertEqual(validate_url(url), url)
        for invalid in [url+"?secret=1", url+"/more", "https://evil.com/share/"+url.rsplit("/",1)[-1]]:
            with self.assertRaises(ExtractionError):
                validate_url(invalid)

    def test_multichunk_utf8_and_ui_text(self):
        conv = {"loaderData": {"route": {"serverResponse": {"data": {
            "title": "測試", "linear_conversation": [
                {"message": {"id": "A", "author": {"role": "user"}, "content": {"parts": ["你好"]}}},
                {"message": {"id": "B", "author": {"role": "assistant"}, "content": {"parts": ["<box>LINE 的文字</box>"]}}}
            ]}}}}}
        encoder = Encoder()
        encoder.add(conv)
        raw = json.dumps(encoder.flat, ensure_ascii=False)
        midpoint = len(raw)//2
        html = "".join("streamController.enqueue("+json.dumps(p, ensure_ascii=False)+");" for p in [raw[:midpoint], raw[midpoint:]])
        result = parse_html(html)
        self.assertEqual(result["report"]["readable_messages"], 2)
        self.assertEqual(result["messages"][1]["text"], "<box>LINE 的文字</box>")
        self.assertEqual([m["role"] for m in result["messages"]], ["user", "assistant"])

    def test_incomplete_page_fails(self):
        with self.assertRaises(ExtractionError):
            parse_html("<html>no share data</html>")

    def test_active_branch(self):
        from chatkeep import normalize
        mapping={"root":{"parent":None,"message":{"id":"1","author":{"role":"user"},"content":{"text":"start"}}},
                 "next":{"parent":"root","message":{"id":"2","author":{"role":"assistant"},"content":{"text":"reply"}}},
                 "other":{"parent":"root","message":{"id":"3","author":{"role":"assistant"},"content":{"text":"not selected"}}}}
        result=normalize({"title":"branch","mapping":mapping,"current_node":"next"})
        self.assertEqual([x["text"] for x in result["messages"]], ["start", "reply"])

if __name__=="__main__":
    unittest.main()
