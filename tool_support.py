"""Host-side tool adapters, target context and Python-3.9 input checks."""
import ast, functools, inspect, json
from pathlib import Path
from bridge import execute, TARGET_DOCUMENT
RUNTIME=Path(__file__).with_name('runtime_ops.py')

def targeted(mcp):
    def decorate(fn):
        @functools.wraps(fn)
        def wrapped(*args,document_id=None,**kwargs):
            token=TARGET_DOCUMENT.set(document_id or TARGET_DOCUMENT.get())
            try:return fn(*args,**kwargs)
            finally:TARGET_DOCUMENT.reset(token)
        signature=inspect.signature(fn)
        wrapped.__signature__=signature.replace(parameters=[*signature.parameters.values(),
            inspect.Parameter('document_id',inspect.Parameter.KEYWORD_ONLY,default=None,annotation=str|None)])
        wrapped.__doc__=(fn.__doc__ or '')+' Optional document_id is PID:runtime_serial from rhino_list_documents; stale or cross-process targets are rejected.'
        return mcp.tool()(wrapped)
    return decorate

def check_code(code):
    tree=ast.parse(code,feature_version=(3,9))
    for n in ast.walk(tree):
        if isinstance(n,ast.Import) and any(x.name.split('.')[0] in {'subprocess','multiprocessing'} for x in n.names):raise ValueError('Never spawn processes inside Rhino')
        if isinstance(n,ast.ImportFrom) and (n.module or '').split('.')[0] in {'subprocess','multiprocessing'}:raise ValueError('Never spawn processes inside Rhino')
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='os' and (n.func.attr in {'system','popen','fork'} or n.func.attr.startswith(('spawn','exec'))):raise ValueError('Never spawn processes inside Rhino')
    return code

def runtime_call(operation,timeout=60,**kwargs):
    code="_ns={}\nexec(compile(open(%r).read(),%r,'exec'),_ns)\nresult=_ns[%r](**%r)" % (str(RUNTIME),str(RUNTIME),operation,kwargs)
    return execute(code,timeout=timeout,operation=operation)
