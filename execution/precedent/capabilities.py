"""Preflight declared model requirements using local metadata, never inference."""
import json,urllib.request

HERMES_MIN_CONTEXT=64000

def model_context(model):
    request=urllib.request.Request('http://127.0.0.1:11434/api/show',data=json.dumps({'model':model}).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=3) as response:
        raw=response.read(1_000_001)
    if len(raw)>1_000_000:raise ValueError('Model metadata size limit')
    data=json.loads(raw);info=data.get('model_info',{});architecture=info.get('general.architecture')
    value=info.get(str(architecture)+'.context_length')
    if type(value) is not int or value<=0:raise ValueError('Model context length is not declared')
    return value

def check(adapter,model):
    from .adapters import CATALOG
    if adapter not in {entry['id'] for entry in CATALOG}:raise ValueError('Unknown adapter')
    if adapter!='hermes':return {'adapter':adapter,'model':model,'status':'no_declared_model_requirement','inference_performed':False,'authentication':'not_checked'}
    result={'adapter':adapter,'model':model,'minimum_context_tokens':HERMES_MIN_CONTEXT,'inference_performed':False,'authentication':'not_checked','scope':'Declared model context only; does not guarantee runtime availability or prompt fit'}
    try:
        value=model_context(model);result['declared_context_tokens']=value
        result['status']='compatible' if value>=HERMES_MIN_CONTEXT else 'incompatible'
    except Exception as error:result.update(status='unverified',reason=str(error))
    return result

def require_compatible(adapter,model):
    if adapter!='hermes':return
    result=check(adapter,model)
    if result['status']!='compatible':
        detail=str(result.get('declared_context_tokens','未確認'))
        raise ValueError('Hermesには64000以上の文脈長が必要です。'+model+' の申告値: '+detail+'。モデルを確認してください。推論は開始していません。')
