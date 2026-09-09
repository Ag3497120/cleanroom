import type { Terminal } from '@xterm/xterm';
import { commandTerminal } from './command-terminal.ts';

const texts = {
 ja: {welcome:'Verantyx — 作業を依頼し、使った判断と学ぶ項目を残す', help:'/login GitHubログイン · /models モデル一覧\n/model inspection 番号 · /model implementation 番号\n/lang ja|en|zh-Hans|ko|es · /status · /cancel\n検査補助と実装案のモデルを選び、依頼文をEnterで送信します。Mac側で許可後に実行します。', login:'先に /login でGitHubへログインしてください。', choose:'先に2つの担当モデルを選んでください。', offline:'計算資源の接続先が未設定です。公開設定の完了後に利用できます。', waiting:'Macで計算資源の使用許可を待っています。', busy:'処理中です。取消は /cancel。', done:'結果を受け取りました。本体への採用は行っていません。', failed:'完了していません', cancelled:'取消を要求しました。', unknown:'パラメータ数不明・選択不可', owner:'SparkはMac所有者の契約を使う本人専用です。', cap:'2モデル合計40B以下・同一アカウントは1日1依頼', approved:'許可済み・実行待ち', running:'Macで処理中', select:'選択', loginCode:'GitHubログイン', notModel:'番号を確認してください。', effort:'推論: 軽（Spark low／ローカルthinking OFF）' },
 en: {welcome:'Verantyx — Work, reusable decisions, and learning',help:'/login GitHub sign-in · /models List models\n/model inspection NUMBER · /model implementation NUMBER\n/lang ja|en|zh-Hans|ko|es · /status · /cancel\nChoose two models, then press Enter to request work. Your Mac owner must approve execution.',login:'Sign in with /login first.',choose:'Choose both models first.',offline:'The compute gateway is not configured yet.',waiting:'Waiting for permission on the Mac.',busy:'A request is in progress. Use /cancel.',done:'Result received. Nothing has been adopted into the main project.',failed:'Not completed',cancelled:'Cancellation requested.',unknown:'Parameter count unknown — unavailable',owner:'Spark uses the Mac owner’s subscription for their own requests only.',cap:'Two models: at most 40B total · one request per account per day',approved:'Approved; waiting to run',running:'Running on the Mac',select:'Selected',loginCode:'GitHub sign-in',notModel:'Check the model number.',effort:'Reasoning: low (Spark low / local thinking OFF)' },
 'zh-Hans': {welcome:'Verantyx — 工作、可复用判断与学习',help:'/login GitHub登录 · /models 模型列表\n/model inspection 编号 · /model implementation 编号\n/lang ja|en|zh-Hans|ko|es · /status · /cancel\n选择两个模型，按Enter提交。Mac所有者批准后执行。',login:'请先使用 /login 登录。',choose:'请先选择两个模型。',offline:'计算资源尚未连接。',waiting:'等待Mac所有者批准。',busy:'正在处理。使用 /cancel 取消。',done:'已收到结果，尚未合入主项目。',failed:'未完成',cancelled:'已请求取消。',unknown:'参数量未知，无法选择',owner:'Spark仅供Mac所有者本人使用订阅。',cap:'两个模型合计不超过40B，每个账号每天一次请求',approved:'已批准，等待执行',running:'正在Mac上处理',select:'已选择',loginCode:'GitHub登录',notModel:'请检查模型编号。',effort:'推理：轻量（Spark low / 本地thinking关闭）'},
 ko: {welcome:'Verantyx — 작업, 재사용할 판단, 학습',help:'/login GitHub 로그인 · /models 모델 목록\n/model inspection 번호 · /model implementation 번호\n/lang ja|en|zh-Hans|ko|es · /status · /cancel\n두 모델을 고른 뒤 Enter로 요청합니다. Mac 소유자가 승인하면 실행합니다.',login:'먼저 /login 으로 로그인하세요.',choose:'두 모델을 먼저 선택하세요.',offline:'계산 자원 연결이 아직 설정되지 않았습니다.',waiting:'Mac 소유자의 승인을 기다립니다.',busy:'처리 중입니다. 취소는 /cancel.',done:'결과를 받았습니다. 본 프로젝트에는 반영하지 않았습니다.',failed:'미완료',cancelled:'취소를 요청했습니다.',unknown:'매개변수 수를 알 수 없어 선택할 수 없습니다',owner:'Spark 구독은 Mac 소유자 본인만 사용합니다.',cap:'두 모델 합계 40B 이하 · 계정당 하루 한 번',approved:'승인됨, 실행 대기',running:'Mac에서 처리 중',select:'선택됨',loginCode:'GitHub 로그인',notModel:'모델 번호를 확인하세요.',effort:'추론: 낮음 (Spark low / 로컬 thinking 끄기)'},
 es: {welcome:'Verantyx — Trabajo, decisiones reutilizables y aprendizaje',help:'/login Acceder con GitHub · /models Modelos\n/model inspection NÚMERO · /model implementation NÚMERO\n/lang ja|en|zh-Hans|ko|es · /status · /cancel\nElige dos modelos y pulsa Enter. El propietario del Mac debe autorizar la ejecución.',login:'Primero inicia sesión con /login.',choose:'Elige ambos modelos primero.',offline:'El equipo de cálculo aún no está conectado.',waiting:'Esperando autorización en el Mac.',busy:'Hay una solicitud en curso. Usa /cancel.',done:'Resultado recibido. No se ha incorporado al proyecto principal.',failed:'Sin completar',cancelled:'Cancelación solicitada.',unknown:'Cantidad de parámetros desconocida; no disponible',owner:'Spark está reservado al propietario del Mac y su suscripción.',cap:'Máximo 40B entre ambos modelos · una solicitud diaria por cuenta',approved:'Autorizado; esperando ejecución',running:'Procesando en el Mac',select:'Seleccionado',loginCode:'Acceso con GitHub',notModel:'Comprueba el número del modelo.',effort:'Razonamiento: bajo (Spark low / thinking local desactivado)'},
};
type Locale = keyof typeof texts;
type Model = {name:string; parameters:number|null; digest:string; provider:string};
type Catalog = {models:Model[];spark:{name:string;available:boolean};identity:{subject:string;login:string}|null};
const fallbackNotice = {ja:'主Macが使用中なら、予備Macの小型2モデル（合計10B以下）へ自動切替します。番号を1つずつ入力すると検査補助→実装案の順に選べます。',en:'When the main Mac is busy, two smaller backup models (up to 10B total) are used. Enter numbers one at a time: inspection, then implementation.', 'zh-Hans':'主Mac忙碌时自动使用备用Mac的两个小模型（合计不超过10B）。依次输入检查、实现模型编号。',ko:'주 Mac 사용 중에는 예비 Mac의 작은 모델 두 개(합계 10B 이하)로 전환합니다. 검사, 구현 순서로 번호를 입력하세요.',es:'Si el Mac principal está ocupado, se usan dos modelos auxiliares (hasta 10B en total). Introduce primero el número de inspección y después el de implementación.'};
const routingText = {ja:'現在混雑しているか、予備Macが接続されていません。少し待ってから同じ依頼を再送するか、後でもう一度お越しください。利用枠は消費していません。',en:'Compute is busy or the backup Mac is offline. Wait and resend, or return later. No daily allowance was used.', 'zh-Hans':'计算资源忙碌或备用Mac离线。请稍后重试，未消耗每日次数。',ko:'계산 자원이 사용 중이거나 예비 Mac이 오프라인입니다. 나중에 다시 시도하세요. 이용 횟수는 차감되지 않았습니다.',es:'Los equipos están ocupados o el Mac auxiliar está desconectado. Vuelve a intentarlo más tarde. No se ha usado tu cuota.'};
const errors: Record<string,string> = {PAIR_OVER_40B:'40B limit',DISTINCT_MODELS_REQUIRED:'Choose different models',PARAMETERS_UNKNOWN:'Unknown model size',ONE_REQUEST_PER_DAY:'Daily account allowance used',SPARK_OWNER_ONLY:'Spark: owner only',SPARK_DAILY_LIMIT:'Daily Spark allowance reached',MODEL_CHANGED_REAPPROVE:'Model changed; new approval required',LOGIN_REQUIRED:'Use /login',GITHUB_LOGIN_NOT_CONFIGURED:'GitHub login is not configured'};

export function remoteTerminal(term: Terminal, gateway: string, status: (value:string)=>void) {
  let choosingLanguage=true;
  let locale:Locale = 'ja', token='', models:Model[]=[], inspection='', implementation='', job='', busy=false, closed=false;
  const abort = new AbortController();
  const label = () => texts[locale];
  const ui = commandTerminal(term, value => { void handle(value); }, () => { void cancel(); });
  const refreshFooter = () => { ui.footer(locale+' · '+(inspection||'inspection: —')+' / '+(implementation||'implementation: —')); };
  const setStatus = (value:string) => { status(value); };
  const delay = (ms:number) => new Promise<void>(resolve=>setTimeout(resolve,ms));
  const api = async <T,>(path:string, method='GET', body?:unknown):Promise<T> => {
    if (!gateway) throw Error(label().offline);
    const r=await fetch(gateway+path,{method,signal:abort.signal,headers:{...(token?{Authorization:'Bearer '+token}:{}),...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});
    const data=await r.json() as T & {error?:string};
    if (!r.ok) throw Error(data.error==='MODEL_SELECTION_NOT_REQUEST'?label().choose:data.error==='COMPUTE_BUSY'?routingText[locale]:errors[data.error??'']??data.error??String(r.status));
    return data;
  };
  const catalog = async () => {
    const data=await api<Catalog>('/v1/models');models=data.models;
    if(data.spark.available) models.push({name:data.spark.name,parameters:0,digest:'subscription-owner-only',provider:'codex'});
    ui.write(models.map((m,i)=>'['+String(i+1)+'] '+m.name+'  '+(m.parameters===null?label().unknown:m.provider==='codex'?'ChatGPT / low':String(m.parameters/1e9)+'B')).join('\n'));
    ui.write(label().owner+'\n'+label().cap+'\n'+label().effort+'\n'+fallbackNotice[locale]);
  };
  async function cancel() {
    if(!job) return;
    try { await api('/v1/jobs/'+encodeURIComponent(job),'DELETE');ui.write(label().cancelled); }
    catch(e) { ui.write(String(e)); }
  }
  async function handle(value:string) {
    let text=value.trim();if(!text||closed)return;
    let ownsBusy=false;
    try {
      if(choosingLanguage){
        const langs:Locale[]=['ja','en','zh-Hans','ko','es'];
        const chosen=langs[Number(text)-1]??(text.replace('/lang ','') as Locale);
        if(!(chosen in texts)){ui.write('1 日本語 · 2 English · 3 简体中文 · 4 한국어 · 5 Español');return;}
        locale=chosen;choosingLanguage=false;document.documentElement.lang=locale;
        ui.write(label().welcome+'\n'+label().help+'\n'+label().cap);refreshFooter();
        if(gateway)await catalog();else ui.write(label().offline);
        return;
      }
      if(text==='verantyx setup'||text==='/setup'){
        ui.write(label().help);await catalog();
        ui.write('/model inspection 2\n/model implementation 1');return;
      }
      {
        const pair=text.match(/^(\d+)\s*(?:と|,|and|&)\s*(\d+)$/);
        if(pair){if(busy){ui.write(label().busy);return;}inspection='';implementation='';await handle('/model inspection '+pair[1]);await handle('/model implementation '+pair[2]);return;}
        const index=models.findIndex(m=>m.name===text);
        if(/^\d+$/.test(text)||index>=0){
          if(busy){ui.write(label().busy);return;}
          if(inspection&&implementation){inspection='';implementation='';refreshFooter();}
          text='/model '+(!inspection?'inspection':'implementation')+' '+(index>=0?index+1:text);
        }
      }
      if(text.startsWith('/lang ') && !text.includes('\n')) {
        const lang=text.slice(6).trim();
        if(!(lang in texts)){ui.write('ja · en · zh-Hans · ko · es');return;}
        locale=lang as Locale;document.documentElement.lang=locale;ui.write(label().help);refreshFooter();return;
      }
      if(text==='/help'){ui.write(label().help);return;}
      if(text==='/cancel'){await cancel();return;}
      if(text==='/logout'&&!busy){token='';setStatus(label().login);return;}
      if(busy){ui.write(label().busy);return;}
      if(text==='/models'){await catalog();return;}
      if(text==='/status'){ui.write(label().cap+'\n'+label().effort+'\n'+inspection+' / '+implementation);return;}
      if(text.startsWith('/model ')&&!text.includes('\n')){
        const [,role,n]=text.split(/\s+/);const m=models[Number(n)-1];
        if(!m||!['inspection','implementation'].includes(role)){ui.write(label().notModel);return;}
        if(m.parameters===null){ui.write(label().unknown);return;}
        const other=models.find(x=>x.name===(role==='inspection'?implementation:inspection));
        if(other&&(other.digest===m.digest||other.name===m.name))throw Error(errors.DISTINCT_MODELS_REQUIRED);
        if((m.parameters??0)+(other?.parameters??0)>40e9)throw Error(errors.PAIR_OVER_40B);
        if(role==='inspection')inspection=m.name;else implementation=m.name;
        ui.write(label().select+': '+m.name);refreshFooter();return;
      }
      if(text==='/login'){
        busy=true;ownsBusy=true;
        const flow=await api<{flow:string;code:string;url:string;interval:number}>('/v1/login/start','POST',{});
        ui.write(label().loginCode+'\n'+flow.url+'\n'+flow.code);
        const deadline=Date.now()+900000;let interval=flow.interval;
        while(!closed&&Date.now()<deadline){
          await delay(interval*1000);if(closed)return;
          const result=await api<{pending?:boolean;interval?:number;token?:string;login?:string}>('/v1/login/poll','POST',{flow:flow.flow});
          if(result.token){token=result.token;ui.write('GitHub: '+result.login);setStatus('GitHub: '+result.login);await catalog();break;}
          interval=result.interval??interval;
        }
        return;
      }
      if(text.startsWith('/')){ui.write(label().help);return;}
      if(!token){ui.write(label().login);return;}
      if(!inspection||!implementation){ui.write(label().choose+'\n/model inspection 2\n/model implementation 1\n'+label().select+': inspection → implementation');return;}
      busy=true;ownsBusy=true;
      const accepted=await api<{id:string;status:string;compute?:{node:string;inspection:string;implementation:string}}>('/v1/jobs','POST',{request:value,locale,inspection,implementation,key:crypto.randomUUID()});
      job=accepted.id;if(accepted.compute)ui.write(accepted.compute.node+' · inspection: '+accepted.compute.inspection+' / implementation: '+accepted.compute.implementation);ui.write(label().waiting);setStatus(label().waiting);
      let previous='';
      while(!closed){
        const result=await api<{status:string;result?:{answer?:string;error?:string;learning?:unknown[];reuse?:unknown[];proposed_files?:Record<string,string>}}>('/v1/jobs/'+encodeURIComponent(job));
        if(result.status!==previous){
          previous=result.status;
          if(result.status==='RUNNING')setStatus(label().running);
          if(result.status==='APPROVED')setStatus(label().approved);
        }
        if(!['PENDING','APPROVED','RUNNING'].includes(result.status)){
          if(result.status==='SUCCEEDED'){
            ui.write(result.result?.answer??'');
            for(const [path,content] of Object.entries(result.result?.proposed_files??{}))ui.write('\n'+path+'\n'+content);
            if(result.result?.learning?.length)ui.write(JSON.stringify({learning:result.result.learning},null,2));
            if(result.result?.reuse?.length)ui.write(JSON.stringify({reuse:result.result.reuse},null,2));
            ui.write(label().done);setStatus(label().done);
          }else{ui.write(label().failed+': '+result.status+' '+(result.result?.error??''));setStatus(label().failed);}
          job='';break;
        }
        await delay(1500);
      }
    }catch(e){if(!closed){ui.write(label().failed+': '+String(e));setStatus(label().failed);}}
    finally{if(ownsBusy)busy=false;}
  }
  ui.write('Language / 言語を選択\n1 日本語\n2 English\n3 简体中文\n4 한국어\n5 Español\n1–5 → Enter');
  refreshFooter();setStatus(gateway?label().login:label().offline);

  return {input(data:string){ui.input(data);},resize(){ui.resize();},dispose(){closed=true;abort.abort();ui.dispose();}};
}
