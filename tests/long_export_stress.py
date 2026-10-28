"""Synthetic isolated batch 5 probes. Emits metrics only, never conversation data."""
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from conversation_export import export_conversation
from word_export import ExportError


def fixture(case):
    if case == 'medium': texts = [('中文abcd'*5000) for _ in range(20)]
    elif case == 'many-messages': texts = ['訊息%04d'%i for i in range(5000)]
    elif case == 'old-counter': texts = ['```text\n'+('<'*10000)+'\n```' for _ in range(20)]
    elif case == 'lines': texts = [('line\n'*1000) for _ in range(100)]
    elif case == 'tables': texts = ['|A|B|C|\n|---|---|---|\n'+'|a|b|c|\n'*200 for _ in range(10)]
    elif case == 'code-blocks': texts = [('```python\nprint(1)\n```\n'*200) for _ in range(20)]
    elif case == 'max-text': texts = [('字abcde'*10000) for _ in range(80)]
    elif case in ('entropy', 'entropy-zip'):
        import random
        rng = random.Random(517)
        texts = [''.join(rng.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',k=60000)) for _ in range(80)]
        if case == 'entropy-zip': texts = [t[:50000]+'\nline'*1000 for t in texts]
    elif case == 'large-message': texts = ['```text\n'+'line\n'*80000+'```']
    elif case == 'volume-overflow': texts = [('x\n'*4000) for _ in range(300)]
    elif case == 'table-overflow': texts = ['|A|B|C|\n|---|---|---|\n'+'|a|b|c|\n'*2000]
    elif case == 'unmatched-code': texts = ['`'*99999+'<box>literal</box>']
    else: raise ValueError(case)
    return {'schema_version':'1.0', 'title':'合成壓力測試', 'report':{'warnings':[]},
            'messages':[{'id':str(i), 'role':'user' if i%2==0 else 'assistant',
                         'text':text} for i,text in enumerate(texts)]}


def worker(case):
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_AS,(384*1024**2,384*1024**2))
    resource.setrlimit(resource.RLIMIT_CPU,(30,31))
    model = fixture(case)
    started = time.monotonic(); cpu = time.process_time()
    try:
        packet = export_conversation(model,'share_link')
        evidence = {'result':packet['artifact_type'], 'volumes':packet['report']['docx_volume_count'],
                    'output_bytes':len(packet['data']), 'messages':packet['report']['output_message_count'],
                    'peak_volume_elements':max(p['structure']['elements']for p in packet['report']['volumes']),
                    'peak_volume_xml_bytes':max(p['structure']['xml_bytes']for p in packet['report']['volumes'])}
    except ExportError as exc: evidence = {'result':'rejected', 'code':exc.code}
    evidence.update(case=case, wall_seconds=round(time.monotonic()-started,3),
                    cpu_seconds=round(time.process_time()-cpu,3),
                    peak_rss_mib=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1))
    print(json.dumps(evidence))


if __name__ == '__main__':
    if len(sys.argv)>1: worker(sys.argv[1])
    else:
        print(json.dumps({'python':platform.python_version(), 'platform':platform.platform(),
                          'cpu_visible':os.cpu_count(), 'limits':'384 MiB AS, 30/31s CPU, 45s wall',
                          'rss':'getrusage ru_maxrss; isolated child including fixture construction'}))
        for case in ('medium','many-messages','old-counter','lines','tables','code-blocks','max-text','entropy','entropy-zip','large-message','volume-overflow','table-overflow','unmatched-code'):
            try:
                p = subprocess.run([sys.executable,__file__,case],capture_output=True,timeout=45)
                print(p.stdout.decode().strip() if p.returncode==0 else json.dumps({'case':case,'returncode':p.returncode}))
            except subprocess.TimeoutExpired: print(json.dumps({'case':case,'result':'wall_timeout'}))
