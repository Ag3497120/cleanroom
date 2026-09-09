"""Conservative observed changes, not LLM declarations of correctness."""
import ast,sys

def surface(source):
    tree=ast.parse(source);api={};imports=set()
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and not node.name.startswith('_'):
            api[node.name]=ast.dump(node.args,include_attributes=False)
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):imports.update(a.name.split('.')[0] for a in node.names)
        if isinstance(node,ast.ImportFrom) and node.module:imports.add(node.module.split('.')[0])
    return api,imports

def detect(before,after):
    events=[]
    for path,new in after.items():
        if not path.endswith('.py'):continue
        old_api,old_imports=surface(before.get(path,''));api,imports=surface(new)
        if any(api.get(name)!=signature for name,signature in old_api.items()):events.append({'event':'PUBLIC_API_CHANGE','facts':{'signature_changed':True},'evidence':{'ast_diff':path}})
        added=imports-old_imports-set(sys.stdlib_module_names)
        if added:events.append({'event':'NEW_DEPENDENCY','facts':{'new_dependency':True},'evidence':{'imports':sorted(added)}})
    return events
