"""Offline Safari archive fallback: strict parsing, no remote fetch."""
import base64
import json
import plistlib
import unittest
from unittest.mock import patch
from chatkeep import ExtractionError
from share_archive import extract_archive, MAX_ARCHIVE
from official_worker import result

SHARE='https://chatgpt.com/share/6af41141-2ee4-83ec-a46c-a62ebd9439d6'
def archive(url=SHARE, html=b'<html>streamController.enqueue("test")</html>'):
    return plistlib.dumps({'WebMainResource':{
        'WebResourceURL':url,'WebResourceMIMEType':'text/html',
        'WebResourceData':html}}, fmt=plistlib.FMT_BINARY)

MODEL={'title':'分享對話','messages':[
    {'category':'visible','role':'user','text':'你好'},
    {'category':'visible','role':'assistant','text':'回答'},
    {'category':'hidden','role':'assistant','text':'secret'}],
    'report':{'status':'extracted_unverified','warnings':[],'issues':[]}}

class ShareArchiveTests(unittest.TestCase):
    def test_valid_webarchive_main_html_only(self):
        with patch('share_archive.parse_html',return_value=MODEL) as parse:
            output=extract_archive(archive(),'saved.webarchive')
        self.assertEqual(output['title'],'分享對話')
        parse.assert_called_once_with('<html>streamController.enqueue("test")</html>', SHARE)

    def test_untrusted_url_and_wrong_mime_rejected(self):
        with self.assertRaises(ExtractionError):
            extract_archive(archive(url='https://example.com/private'),'saved.webarchive')
        bad=plistlib.dumps({'WebMainResource':{'WebResourceURL':SHARE,
             'WebResourceMIMEType':'application/pdf','WebResourceData':b'x'}})
        with self.assertRaises(ExtractionError):extract_archive(bad,'saved.webarchive')

    def test_bounded_and_strict(self):
        with self.assertRaises(ExtractionError):extract_archive(b'x'*(MAX_ARCHIVE+1),'saved.webarchive')
        with self.assertRaises(ExtractionError):extract_archive(b'not plist','saved.webarchive')
        with self.assertRaises(ExtractionError):extract_archive(b'<html>fake</html>','saved.pdf')
        with self.assertRaises(ExtractionError):extract_archive(b'<html>fake</html>','saved.html')

    def test_reader_removes_hidden_messages(self):
        body=json.dumps({'filename':'saved.webarchive',
            'data':base64.b64encode(archive()).decode()}).encode()
        with patch('share_archive.parse_html',return_value=MODEL):
            output=result(body,'archive_reader')
        self.assertEqual(output['data']['messages'],[
            {'role':'user','text':'你好'},{'role':'assistant','text':'回答'}])
        self.assertEqual(output['data']['report']['source'],'user_uploaded_archive')

    def test_word_export_uses_existing_converter(self):
        body=json.dumps({'filename':'saved.webarchive',
            'data':base64.b64encode(archive()).decode()}).encode()
        fake={'artifact_type':'docx','filename':'test.docx',
              'mime_type':'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
              'data':b'zipdata','report':{}}
        with patch('share_archive.parse_html',return_value=MODEL),patch('official_worker.export_conversation',return_value=fake) as export:
            output=result(body,'archive_word')
        self.assertEqual(base64.b64decode(output['document']),b'zipdata')
        self.assertEqual(export.call_args.args[1],'share_link')

    def test_real_parser_reader_and_word_end_to_end(self):
        from test_chatkeep import Encoder
        conv = {'loaderData': {'route': {'serverResponse': {'data': {
            'title': '離線封存測試',
            'linear_conversation': [
                {'message': {'id': 'A', 'author': {'role': 'user'}, 'content': {'parts': ['第一句']}}},
                {'message': {'id': 'B', 'author': {'role': 'assistant'}, 'content': {'parts': ['**第二句**']}}}
            ]}}}}}
        encoder=Encoder()
        encoder.add(conv)
        html='streamController.enqueue('+json.dumps(json.dumps(encoder.flat,ensure_ascii=False),ensure_ascii=False)+');'
        body=json.dumps({'filename':'test.webarchive',
            'data':base64.b64encode(archive(html=html.encode())).decode()}).encode()
        reader=result(body,'archive_reader')
        self.assertEqual([m['text'] for m in reader['data']['messages']],['第一句','**第二句**'])
        word=result(body,'archive_word')
        self.assertTrue(word['ok'])
        self.assertIn(word['artifact_type'],('docx','zip'))
        from zipfile import ZipFile
        from io import BytesIO
        with ZipFile(BytesIO(base64.b64decode(word['document']))) as z:
            self.assertIsNone(z.testzip())

    def test_invalid_base64(self):
        with self.assertRaises(ExtractionError):
            result(b'{"filename":"a.webarchive","data":"%%%"}','archive_reader')

if __name__=='__main__':unittest.main()
