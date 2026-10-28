"""Batch 5 bounded local Gunicorn load/RSS and privacy probe; synthetic only."""
import base64
from io import BytesIO
import json
import os
from pathlib import Path
import random
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1]


def memory_tree(pid):
    rows={}
    for path in Path('/proc').glob('[0-9]*/status'):
        try:
            fields=dict(line.split(':',1)for line in path.read_text().splitlines()if ':' in line)
            rows[int(path.parent.name)]=(int(fields['PPid']),int(fields.get('VmRSS','0 kB').split()[0])*1024)
        except (OSError,ValueError,KeyError,ProcessLookupError): pass
    selected={pid}
    while True:
        found={p for p,(parent,_)in rows.items()if parent in selected}
        if found <= selected: break
        selected |= found
    return sum(rows.get(p,(0,0))[1] for p in selected)


def run():
    with socket.socket()as reserved:
        reserved.bind(('127.0.0.1',0));port=reserved.getsockname()[1]
    process=subprocess.Popen([sys.executable,'-m','gunicorn','--config','gunicorn.conf.py','server:application'],
        cwd=ROOT,env=dict(os.environ,PORT=str(port)),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    base='http://127.0.0.1:%d'%port
    stop=threading.Event(); peak=[0]
    def sample():
        while not stop.wait(.01): peak[0]=max(peak[0],memory_tree(process.pid))
    sampler=None
    try:
        for _ in range(50):
            try:
                with urllib.request.urlopen(base,timeout=1):break
            except OSError:time.sleep(.1)
        else:raise AssertionError('readiness failed')
        rng=random.Random(517)
        conv={'title':'PRIVATE_LOAD_TITLE','current_node':'m99','mapping':{}}
        for i in range(100):
            text='PRIVATE_LOAD_BODY_%03d\n'%i+''.join(rng.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',k=8000))+'\nline'*1000
            conv['mapping']['m%d'%i]={'parent':None if i==0 else 'm%d'%(i-1),'message':{
                'id':'m%d'%i,'author':{'role':'assistant'},'content':{'content_type':'text','parts':[text]}}}
        body=json.dumps(conv).encode()
        response_sizes = []
        def post(data):
            request=urllib.request.Request(base+'/api/convert-json',data=data,headers={'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(request,timeout=60)as response:
                    response_sizes.append((len(data),int(response.headers['Content-Length'])))
                    return response.status,json.load(response)
            except urllib.error.HTTPError as exc:return exc.code,json.load(exc)
        baseline=memory_tree(process.pid)
        sampler=threading.Thread(target=sample);sampler.start()
        first=[]
        def convert(): first.append(post(body))
        started=time.monotonic()
        thread=threading.Thread(target=convert);thread.start()
        time.sleep(.1)
        busy=post(b'{}')
        thread.join(timeout=60)
        assert not thread.is_alive() and first
        elapsed=time.monotonic()-started
        assert busy[0]==429 and busy[1]['error']['code']=='BUSY'
        status,packet=first[0]
        assert status==200 and packet['artifact_type']=='zip' and packet['report']['complete']
        output=base64.b64decode(packet['document'])
        with ZipFile(BytesIO(output))as archive:
            assert len(archive.namelist())==packet['report']['docx_volume_count']==2 and archive.testzip()is None
        # Failure and subsequent conversion must not retain the admission slot.
        failed={'title':'synthetic','current_node':'a','mapping':{'a':{'parent':None,'message':{
            'id':'a','author':{'role':'user'},'content':{'content_type':'text','parts':['```\n'+'x\n'*80000+'```']}}}}}
        failure=post(json.dumps(failed).encode())
        assert failure[0]==422 and failure[1]['error']['code']=='MESSAGE_TOO_LARGE'
        failed['mapping']['a']['message']['content']['parts']=['short']
        assert post(json.dumps(failed).encode())[0]==200
        print(json.dumps({'local_gunicorn':'passed','request_bytes':len(body),'artifact_bytes':len(output),
            'base64_characters':len(packet['document']),'http_response_bytes':next(size for length,size in response_sizes if length==len(body)),
            'volumes':packet['report']['docx_volume_count'],'messages':packet['report']['output_message_count'],
            'wall_seconds':round(elapsed,3),'service_rss_baseline_mib':round(baseline/1024**2,1),
            'service_rss_peak_mib':round(peak[0]/1024**2,1),'concurrent_admission':'429 BUSY',
            'failure_then_reuse':'passed','rss_scope':'sum of Gunicorn master/worker/converter RSS; shared pages counted repeatedly; 10ms polling'}))
    finally:
        stop.set()
        if sampler:sampler.join()
        process.terminate()
        try:out,err=process.communicate(timeout=20)
        except subprocess.TimeoutExpired:process.kill();out,err=process.communicate()
        assert b'PRIVATE_LOAD_BODY'not in out+err and b'PRIVATE_LOAD_TITLE'not in out+err


if __name__=='__main__':run()
