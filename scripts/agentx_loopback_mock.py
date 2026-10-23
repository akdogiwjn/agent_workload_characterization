"""Loopback-only chat mock with independently tokenized request capture.

No model, credentials, remote inference, simulated GPU or cache metrics.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
import uuid


def plain_content(messages):
    result=[]
    for message in messages:
        content=message.get('content','')
        if isinstance(content,str):result.append(content)
        elif isinstance(content,list):
            for item in content:
                if item.get('type')=='text':result.append(item.get('text',''))
                else:raise ValueError('mock accepts text only')
        elif content is not None:raise ValueError('invalid content')
    return ''.join(result)


def response_text(tokenizer, count):
    unit=tokenizer.encode(' test',add_special_tokens=False)
    if len(unit)!=1:raise ValueError('response token unit is not singular')
    text=tokenizer.decode(unit*count,skip_special_tokens=False,clean_up_tokenization_spaces=False)
    if len(tokenizer.encode(text,add_special_tokens=False))!=count:
        raise ValueError('response token roundtrip mismatch')
    return text


def serve(tokenizer_path, output, ready_path, delay):
    import numpy as np
    from transformers import AutoTokenizer
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    (output/'requests').mkdir()
    tokenizer=AutoTokenizer.from_pretrained(tokenizer_path,local_files_only=True,trust_remote_code=False)
    guard=threading.Lock()
    @lru_cache(maxsize=512)
    def text_for_count(count):return response_text(tokenizer,count)

    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args):pass

        def do_GET(self):
            if self.path in ['/health','/v1/models']:
                data={'status':'ready','no_model':True} if self.path=='/health' else {'object':'list','data':[{'id':'agentx-mock','object':'model'}]}
                b=json.dumps(data).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
            else:self.send_error(404)

        def do_POST(self):
            if self.path!='/v1/chat/completions':self.send_error(404);return
            received=time.monotonic_ns();received_wall=time.time_ns()
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=64*1024**2:self.send_error(413);return
            body=self.rfile.read(length)
            request_id=self.headers.get('X-Request-ID') or uuid.uuid4().hex
            file_id=hashlib.sha256(request_id.encode()).hexdigest()
            try:
                payload=json.loads(body)
                messages=payload['messages']
                ids=tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_dict=False)
                content_ids=tokenizer.encode(plain_content(messages),add_special_tokens=False)
                requested=payload.get('max_completion_tokens',payload.get('max_tokens'))
                if type(requested) is not int or not 1<=requested<=100000:
                    raise ValueError('invalid requested output length')
                text=text_for_count(requested)
                np.savez_compressed(output/'requests'/f'{file_id}.npz',prompt_ids=np.asarray(ids,dtype=np.int32),content_ids=np.asarray(content_ids,dtype=np.int32))
                with gzip.open(output/'requests'/f'{file_id}.json.gz','wb') as f:f.write(body)
                usage={'prompt_tokens':len(ids),'completion_tokens':requested,'total_tokens':len(ids)+requested}
                base={'id':'chatcmpl-mock-'+file_id[:20],'object':'chat.completion.chunk','created':int(time.time()),'model':payload['model']}
                if payload.get('stream'):
                    chunks=[{**base,'choices':[{'index':0,'delta':{'role':'assistant'},'finish_reason':None}]}]
                    # Preserve the exact requested token count while using modest SSE frames.
                    pieces=[text[i:i+768] for i in range(0,len(text),768)]
                    chunks += [{**base,'choices':[{'index':0,'delta':{'content':piece},'finish_reason':None}]} for piece in pieces]
                    chunks += [{**base,'choices':[{'index':0,'delta':{},'finish_reason':'length'}]}, {**base,'choices':[],'usage':usage}]
                    result=b''.join(b'data: '+json.dumps(q,separators=(',',':')).encode()+b'\n\n' for q in chunks)+b'data: [DONE]\n\n'
                    kind='text/event-stream'
                else:
                    result=json.dumps({**base,'object':'chat.completion','choices':[{'index':0,'message':{'role':'assistant','content':text},'finish_reason':'length'}],'usage':usage},separators=(',',':')).encode();kind='application/json'
                if delay:time.sleep(delay)
                self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(result)));self.send_header('X-Request-ID',request_id);self.end_headers();self.wfile.write(result);self.wfile.flush()
                status='completed'
                row={'request_id':request_id,'file_id':file_id,'correlation_id':self.headers.get('X-Correlation-ID'),
                     'dynamo_session_id':self.headers.get('X-Dynamo-Session-ID'),'dynamo_parent_id':self.headers.get('X-Dynamo-Parent-Session-ID'),
                     'received_monotonic_ns':received,'completed_monotonic_ns':time.monotonic_ns(),'received_wall_ns':received_wall,
                     'body_sha256':hashlib.sha256(body).hexdigest(),'body_bytes':len(body),'model':payload['model'],
                     'stream':bool(payload.get('stream')),'max_tokens':requested,'rendered_input_tokens':len(ids),'content_input_tokens':len(content_ids),
                     'response_tokens':requested,'status':status,'authorization_header_present':self.headers.get('Authorization') is not None,
                     'prompt_ids_sha256':hashlib.sha256(np.asarray(ids,dtype=np.int32).tobytes()).hexdigest()}
            except Exception as error:
                row={'request_id':request_id,'file_id':file_id,'received_monotonic_ns':received,'completed_monotonic_ns':time.monotonic_ns(),
                     'status':'error','error_type':type(error).__name__,'error':str(error)[:400]}
                try:self.send_error(500,str(error)[:100])
                except (BrokenPipeError,ConnectionError):pass
            with guard:
                with (output/'server_requests.jsonl').open('a') as f:f.write(json.dumps(row,separators=(',',':'))+'\n')

    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    ready={'url':f'http://127.0.0.1:{server.server_port}','pid':__import__('os').getpid(),'tokenizer':str(tokenizer_path),
           'binding':'127.0.0.1 only','model_loaded':False,'response_unit':'one tokenizer token: space+test','delay_s':delay}
    Path(ready_path).write_text(json.dumps(ready,indent=2)+'\n')
    try:server.serve_forever(poll_interval=.1)
    finally:server.server_close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--tokenizer',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--ready',type=Path,required=True);p.add_argument('--delay',type=float,default=.01)
    a=p.parse_args();serve(a.tokenizer,a.output,a.ready,a.delay)
