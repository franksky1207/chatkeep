"""Public share HTML route should return only readable data; no DOCX."""
import unittest
from unittest.mock import patch
from official_worker import result

class ShareReaderTests(unittest.TestCase):
    def test_image_reference_keeps_message_and_all_text_for_word(self):
        from chatkeep import normalize
        from conversation_export import export_conversation
        source={'title':'圖片訊息','linear_conversation':[{
            'id':'m1','message':{'id':'m1','author':{'role':'user'},
            'content':{'content_type':'multimodal_text','parts':[
                {'content_type':'image_asset_pointer','asset_pointer':'sediment://file_example',
                 'width':320,'height':240,'size_bytes':100,'mime_type':'image/png','metadata':{}},
                '這張圖怎麼看？']}}}]}
        model=normalize(source)
        self.assertEqual(len(model['messages']),1)
        self.assertEqual(model['messages'][0]['category'],'visible')
        self.assertIn('圖片附件',model['messages'][0]['text'])
        self.assertIn('這張圖怎麼看？',model['messages'][0]['text'])
        self.assertEqual(model['report']['issues'][0]['reason'],'image_reference_not_embedded')
        artifact=export_conversation(model,'share_link')
        self.assertEqual(artifact['artifact_type'],'docx')
        self.assertTrue(artifact['data'].startswith(b'PK'))

    def test_unknown_multimodal_part_still_rejected(self):
        from chatkeep import normalize
        from conversation_export import export_conversation
        from word_export import ExportError
        source={'title':'不支援','linear_conversation':[{
            'id':'m1','message':{'id':'m1','author':{'role':'user'},
            'content':{'content_type':'multimodal_text','parts':[
                {'content_type':'unknown_type','value':'X'},'可見文字']}}}]}
        model=normalize(source)
        self.assertEqual(model['messages'][0]['category'],'non_text')
        with self.assertRaises(ExportError):
            export_conversation(model,'share_link')


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
