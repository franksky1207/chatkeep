import {writeFileSync} from 'node:fs';
import {zipFiles,htmlDocument} from '../docs/local-backup/reader-export.mjs';
const blob=zipFiles([{name:'第一段.html',content:htmlDocument('測試一',[{role:'user',text:'你好'}])},{name:'第二段.html',content:htmlDocument('測試二',[{role:'assistant',text:'| A | B |\n|---|---|\n| 1 | 2 |'}])}]);
writeFileSync('/tmp/chatkeep-reader-zip-check.zip',Buffer.from(await blob.arrayBuffer()));
