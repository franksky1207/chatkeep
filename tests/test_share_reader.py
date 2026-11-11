"""Public share HTML route should return only readable data; no DOCX."""
import unittest
from unittest.mock import patch
from official_worker import result

class ShareReaderTests(unittest.TestCase):
    def test_html_503_uses_same_host_public_json_without_changing_output(self):
        from chatkeep import extract_url, ExtractionError
        url='https://chatgpt.com/share/00000000-0000-0000-0000-000000000000'
        snapshot={'title':'備份','linear_conversation':[
          {'id':'u1','message':{'id':'u1','author':{'role':'user'},'content':{'content_type':'text','parts':['問題']}}},
          {'id':'a1','message':{'id':'a1','author':{'role':'assistant'},'content':{'content_type':'text','parts':['回答']}}},
        ]}
        with patch('chatkeep.fetch_html',side_effect=ExtractionError('分享頁回應 HTTP 503；可能已失效或限制匿名存取')), \
             patch('chatkeep.fetch_share_json',return_value=snapshot) as get_json:
            result=extract_url(url)
        get_json.assert_called_once_with(url)
        self.assertEqual([m['text'] for m in result['messages']],['問題','回答'])
        self.assertEqual(result['provenance']['source'],'public_share_json_after_html_503')

    def test_no_fallback_for_non_503_or_parser_failures(self):
        from chatkeep import extract_url, ExtractionError
        url='https://chatgpt.com/share/00000000-0000-0000-0000-000000000000'
        with patch('chatkeep.fetch_html',side_effect=ExtractionError('分享頁回應 HTTP 403；可能已失效或限制匿名存取')), \
             patch('chatkeep.fetch_share_json') as alternate:
            with self.assertRaises(ExtractionError):
                extract_url(url)
        alternate.assert_not_called()


    def test_safe_diagnostic_categories(self):
        from official_worker import classify_share_failure
        from chatkeep import ExtractionError
        cases = {
            '分享頁回應 HTTP 403；可能已失效或限制匿名存取': 'SOURCE_HTTP_403',
            'No ChatGPT stream found': 'SHARE_FORMAT_UNSUPPORTED',
            'Unsupported turbo-stream tag: Q': 'SHARE_FORMAT_UNSUPPORTED',
            'Active branch and linear conversation disagree': 'CONVERSATION_STRUCTURE_FAILED',
            'HTML exceeds permitted size': 'SOURCE_SIZE_OR_TRUNCATED',
        }
        for raw, expected in cases.items():
            self.assertEqual(classify_share_failure(ExtractionError(raw)), expected)
        self.assertNotIn('https://', classify_share_failure(ExtractionError('https://private.example/secret')))


    def test_server_registers_reader_route(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parent.parent / 'server.py').read_text(encoding='utf-8')
        self.assertIn("'/api/share-reader-v1', '/api/archive-reader-v1', '/api/archive-word-v1'", source)

    def test_share_reader_reuses_extraction(self):
        model={'title':'範例分享','messages':[
          {'category':'visible','role':'user','text':'你好'},
          {'category':'visible','role':'assistant','text':'**你好**'},
          {'category':'hidden','role':'assistant','text':'internal'},
          {'category':'visible','role':'tool','text':'trace'}],
          'report':{'status':'extracted_unverified','issues':[],'warnings':[]}}
        url='https://chatgpt.com/share/00000000-0000-0000-0000-000000000000'
        with patch('chatkeep.extract_url',return_value=model):
            output=result(('{"url":"'+url+'"}').encode(),'share_reader')
        self.assertTrue(output['ok'])
        self.assertEqual(output['data']['messages'],[{'role':'user','text':'你好'},{'role':'assistant','text':'**你好**'}])
        self.assertNotIn('document',output)
    def test_invalid_url_rejected(self):
        from chatkeep import ExtractionError
        with self.assertRaises(ExtractionError):
            result(b'{"url":"https://example.com/private"}','share_reader')

if __name__=='__main__':unittest.main()
