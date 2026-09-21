#!/usr/bin/env python3
"""Persistent, instance-targeted RhinoCode transport. Process spawning is host-only."""
from __future__ import annotations
import contextvars, hashlib, json, math, os, re, subprocess, time, uuid, sys
from pathlib import Path
import fcntl

ROOT = Path(__file__).resolve().parent
RHINOCODE = Path(os.environ.get('RHINOCODE_PATH', '/Applications/Rhino 8.app/Contents/Resources/bin/rhinocode'))
DEFAULT_TIMEOUT = float(os.environ.get('RHINO_MCP_TIMEOUT', '30'))
JOBS = Path(os.environ.get('RHINO_MCP_JOB_DIR', str(Path.home()/'Library/Caches/rhino-cad-mcp/jobs')))
TARGET_DOCUMENT = contextvars.ContextVar('rhino_document', default=None)

class RhinoBridgeError(RuntimeError): pass

def cli_environment():
    env = dict(os.environ)
    repaired = False
    # MCP stdio clients sometimes strip TMPDIR; .NET IPC discovery then searches
    # a different directory from the running macOS Rhino instance.
    if not env.get('TMPDIR') and os.name == 'posix':
        try:
            value = os.confstr('CS_DARWIN_USER_TEMP_DIR')
            if value and Path(value).is_dir(): env['TMPDIR'] = value; repaired = True
        except (ValueError, OSError):
            if sys.platform == 'darwin':
                try:
                    cp = subprocess.run(['/usr/bin/getconf','DARWIN_USER_TEMP_DIR'],capture_output=True,text=True,timeout=2,check=False,env=env)
                    value=cp.stdout.strip()
                    if cp.returncode==0 and value and Path(value).is_dir():env['TMPDIR']=value;repaired=True
                except (OSError,subprocess.SubprocessError):pass
    return env, repaired

def _run_cli(*args, timeout=10.0):
    if not RHINOCODE.is_file(): raise RhinoBridgeError('rhinocode not found: '+str(RHINOCODE))
    env, _ = cli_environment()
    return subprocess.run([str(RHINOCODE), *args], capture_output=True, text=True,
                          timeout=timeout, check=False, env=env)

def parse_instances(raw):
    raw = re.sub(r'\x1b\[[0-9;]*m', '', raw)
    rows = []
    for line in raw.splitlines():
        m = re.match(r'^\s*(\d+)\s+(\S+)(?:\s+(.*))?$', line)
        if m: rows.append({'pid':int(m[1]), 'instance_id':m[2], 'document_hint':(m[3] or '').strip()})
    return rows

def discover():
    env, repaired = cli_environment()
    result = {'rhinocode':str(RHINOCODE), 'environment':{'TMPDIR':env.get('TMPDIR'),
              'tmpdir_repaired':repaired, 'HOME_present':bool(env.get('HOME'))}}
    try:
        cp = _run_cli('list'); instances = parse_instances(cp.stdout or '')
        result.update(ok=cp.returncode == 0 and bool(instances), instances=instances,
                      instances_raw=(cp.stdout or '').strip(), stderr=(cp.stderr or '').strip())
        if not result['ok']: result.update(kind='no_instances', hint='Open Rhino; check TMPDIR and any startup/license dialogs. A header alone is not a connection.')
    except Exception as exc: result.update(ok=False, kind='discovery_error', error=str(exc), instances=[])
    return result

def _choose(instances, document_id=None, instance_id=None):
    chosen = instance_id or os.environ.get('RHINO_INSTANCE_ID')
    pid = None
    if document_id:
        if not re.fullmatch(r'\d+:\d+', str(document_id)): raise ValueError('document_id must be PID:runtime_serial from rhino_list_documents')
        pid = int(str(document_id).split(':')[0])
    matches = [x for x in instances if (pid is None or x['pid']==pid) and
               (not chosen or chosen in (x['instance_id'], str(x['pid'])))]
    if len(matches)!=1: raise ValueError('Target is missing or ambiguous; specify instance_id or a live document_id')
    return matches[0]

def _atomic(path, data):
    tmp=path.with_suffix(path.suffix+'.'+uuid.uuid4().hex+'.tmp')
    tmp.write_text(json.dumps(data, default=str, indent=2)); tmp.replace(path)

def _job_dir(job_id):
    if not re.fullmatch(r'[0-9a-f]{32}', job_id): raise ValueError('Invalid job ID')
    return JOBS/job_id

def job_status(job_id):
    p=_job_dir(job_id)
    if not (p/'request.json').exists(): return {'ok':False,'kind':'job_not_found','job_id':job_id}
    request=json.loads((p/'request.json').read_text())
    if (p/'result.json').exists():
        data=json.loads((p/'result.json').read_text()); data.update(job_id=job_id, state='completed' if data.get('ok') else 'failed')
        return data
    state='running' if (p/'started.json').exists() else 'submitted'
    return {'ok':True,'job_id':job_id,'state':state,'pending':True,'operation':request['operation'],
            'submitted_at':request['submitted_at'],'instance_id':request['instance_id'],
            'document_id':request.get('document_id'),'submission':request.get('submission'),
            'note':'Pending does not mean canceled. Retrieve this job; do not resubmit the mutation.'}

def wait_job(job_id, timeout=30):
    if not math.isfinite(timeout) or not 0<=timeout<=600: raise ValueError('timeout must be 0..600 seconds')
    deadline=time.monotonic()+timeout
    while True:
        data=job_status(job_id)
        if not data.get('pending') or time.monotonic()>=deadline: return data
        time.sleep(.05)

def list_jobs(limit=30):
    if not JOBS.exists(): return []
    dirs=sorted((p for p in JOBS.iterdir() if p.is_dir() and re.fullmatch('[0-9a-f]{32}',p.name)), key=lambda p:p.stat().st_mtime, reverse=True)
    return [job_status(p.name) for p in dirs[:max(1,min(limit,200))]]

def execute(code, timeout=None, operation='mcp', undoable=True, document_id=None,
            instance_id=None, idempotency_key=None, wait=True, _discovery=None):
    timeout=DEFAULT_TIMEOUT if timeout is None else float(timeout)
    if not math.isfinite(timeout) or not 0<=timeout<=600: return {'ok':False,'kind':'invalid_timeout'}
    document_id=document_id or TARGET_DOCUMENT.get()
    st=_discovery or discover()
    if not st['ok']: return {'ok':False,'kind':'rhino_unavailable','status':st}
    try: target=_choose(st['instances'],document_id,instance_id)
    except ValueError as exc: return {'ok':False,'kind':'target_error','error':str(exc),'instances':st['instances']}
    JOBS.mkdir(parents=True,exist_ok=True,mode=0o700)
    fingerprint=hashlib.sha256(json.dumps([code,document_id,target['instance_id'],operation]).encode()).hexdigest()
    # Host filesystem lock prevents duplicate idempotent submissions across MCP clients.
    with (JOBS/'.submit.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        index=JOBS/('key-'+hashlib.sha256(idempotency_key.encode()).hexdigest()+'.json') if idempotency_key else None
        if index and index.exists():
            prior=json.loads(index.read_text())
            if prior['fingerprint']!=fingerprint: return {'ok':False,'kind':'idempotency_conflict','job_id':prior['job_id']}
            job_id=prior['job_id']; new=False
        else:
            job_id=uuid.uuid4().hex; p=JOBS/job_id; p.mkdir(mode=0o700)
            request={'job_id':job_id,'operation':operation,'instance_id':target['instance_id'],
                     'document_id':document_id,'submitted_at':time.time(),'fingerprint':fingerprint}
            _atomic(p/'request.json',request)
            (p/'script.py').write_text(_make_harness(code,p/'result.json',job_id,operation,document_id))
            if index: _atomic(index,{'job_id':job_id,'fingerprint':fingerprint})
            new=True
        if new:
            try:
                cp=_run_cli('-r',target['instance_id'],'script',str(p/'script.py'),timeout=10)
                request['submission']={'returncode':cp.returncode,'stdout':cp.stdout,'stderr':cp.stderr}
            except Exception as exc:
                request['submission']={'uncertain':True,'error':str(exc)}
            _atomic(p/'request.json',request)
    result=wait_job(job_id,timeout) if wait else job_status(job_id)
    if result.get('pending'): result['timeout_seconds']=timeout
    return result

def status(instance_id=None, ping_timeout=8):
    st=discover()
    if not st['ok']: return st
    pong=execute("result={'ping':'pong'}",timeout=ping_timeout,operation='status_ping',instance_id=instance_id,_discovery=st)
    st.update(ok=bool(pong.get('ok') and not pong.get('pending') and (pong.get('result') or {}).get('ping')=='pong'),ping=pong)
    if not st['ok']: st['kind']='ping_failed_or_pending'
    return st

def _make_harness(code,result_path,op_id,operation,document_id=None):
    # Runtime payload is deliberately compatible with Rhino's Python 3.9.
    return '''import contextlib, io, json, time, traceback, os
from pathlib import Path
import Rhino, scriptcontext as sc
_RESULT_PATH=Path(%r)
_started=time.time()
_buf=io.StringIO()
_original_doc=sc.doc
_target_id=%r
_actual_id=None
result=None
_payload={}
def _write(path,data):
    t=Path(str(path)+'.tmp');t.write_text(json.dumps(data,default=str));t.replace(path)
try:
    _write(_RESULT_PATH.parent/'started.json',{'started_at':time.time()})
    if _target_id:
        _pid,_serial=[int(x) for x in _target_id.split(':')]
        if _pid!=os.getpid():raise RuntimeError('Wrong Rhino process for document target')
        _doc=Rhino.RhinoDoc.FromRuntimeSerialNumber(_serial)
        if _doc is None:raise RuntimeError('Document target is closed or stale')
        sc.doc=_doc
    elif Rhino.RhinoDoc.ActiveDoc is not None:
        sc.doc=Rhino.RhinoDoc.ActiveDoc
    if sc.doc is not None:_actual_id=str(os.getpid())+':'+str(sc.doc.RuntimeSerialNumber)
    with contextlib.redirect_stdout(_buf),contextlib.redirect_stderr(_buf):
%s
    _payload={'ok':True,'result':result}
except Exception as exc:
    _payload={'ok':False,'kind':'python_exception','error':str(exc),'traceback':traceback.format_exc()}
finally:
    if _target_id:sc.doc=_original_doc
    _payload.update(operation_id=%r,operation=%r,document_id=_actual_id,console=_buf.getvalue(),rhino_elapsed_ms=round((time.time()-_started)*1000,1))
    _write(_RESULT_PATH,_payload)
''' % (str(result_path),document_id,_indent(code,8),op_id,operation)

def _indent(text,spaces): return '\n'.join(' '*spaces+line for line in (text.splitlines() or ['pass']))
