"""Public share HTML route should return only readable data; no DOCX."""
import unittest
from unittest.mock import patch
from official_worker import result

class ShareReaderTests(unittest.TestCase):
    def test_server_registers_reader_route(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parent.parent / 'server.py').read_text(encoding='utf-8')
        self.assertIn("if path in ('/api/convert-json', '/api/convert-v2', '/api/convert-chunk-v1', '/api/share-reader-v1'):", source)

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
