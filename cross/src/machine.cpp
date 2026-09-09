#include "cross.hpp"
#include <algorithm>
#include <limits>
#include <random>
#include <sstream>

namespace cross {
bool is_value(const std::string& c){return c=="整数"||c=="小数"||c=="文章"||c=="真偽"||c=="無"||c=="列"||c=="空列"||c=="記録"||c=="計画の値"||c=="失敗"||c=="十字の値"||c=="格子の値"||c=="セル束"||c=="格子の進行";}
std::vector<std::string> roles(const std::string& op){
    if(op=="参照")return {"対象"};
    if(op=="足す"||op=="引く"||op=="掛ける"||op=="割る"||op=="以下"||op=="等しい"||op=="つなぐ"||op=="対にする")return {"左","右"};
    if(op=="先頭"||op=="残り"||op=="空か")return {"値"};
    if(op=="選ぶ")return {"条件","真の枝","偽の枝"};
    if(op=="呼ぶ")return {"計画","入力"};auto structural=structural_roles(op);return structural.empty()?grid_roles(op):structural;
}
std::string operation(const Space& s,const std::string& center){
    if(!roles(center).empty()||s.root<0)return center;
    Id registry=s.ref(s.root,"規則集");if(registry<0)return center;
    for(Id i:s.items(registry))if(s.at(i).center=="語義"&&s.text(i,"表現")==center)return s.text(i,"動き");return center;
}
Id result(const Space& s,Id n){const auto& node=s.at(n);if(is_value(node.center))return n;return node.port("結果").vertices[0].ref;}
Id instantiate(Space& s,Id body,const std::map<Id,Id>& substitutions){
    std::map<Id,Id> memo=substitutions;std::vector<Id> todo{body};
    while(!todo.empty()){
        Id id=todo.back();todo.pop_back();if(memo.count(id))continue;const Node node=s.at(id);
        if(is_value(node.center)){memo[id]=id;continue;}
        if(node.center=="引数")throw std::runtime_error("引数が束縛されていません");
        auto inputs=roles(operation(s,node.center));if(inputs.empty())throw std::runtime_error("展開できない中心です: "+node.center);
        memo[id]=s.add(node.center);
        for(const auto& role:inputs){const auto a=node.port(role);for(Id target:{a.edges[0].ref,a.edges[2].ref,a.vertices[0].ref})if(target>=0)todo.push_back(target);}
    }
    for(const auto& [source,target]:memo){
        if(source==target||substitutions.count(source))continue;const Node node=s.at(source);const auto inputs=roles(operation(s,node.center));
        for(int i=0;i<6;++i){const auto& a=node.arms[i];if(std::find(inputs.begin(),inputs.end(),a.faces[0].text)==inputs.end())continue;
            Arm copied=a;for(int e:{0,2})if(copied.edges[e].ref>=0)copied.edges[e].ref=memo.at(copied.edges[e].ref);
            if(copied.vertices[0].ref>=0)copied.vertices[0].ref=memo.at(copied.vertices[0].ref);
            s.at(target).arms[i]=copied;
        }
    }
    return memo.at(body);
}
Machine::Machine(Space& space):s(space) {
    s.validate();
    if(s.at(s.root).center!="計算空間")throw std::runtime_error("実行する計算空間ではありません");
    Id registry=s.ref(s.root,"規則集");
    if(registry>=0)for(Id i:s.items(registry))if(s.at(i).center=="語義")
        aliases.emplace(s.text(i,"表現"),s.text(i,"動き"));
}
std::string Machine::resolve(const std::string& center) const {
    auto it=aliases.find(center);
    return it==aliases.end()?center:it->second;
}
Id Machine::output()const{return s.ref(s.root,"実行");}
void Machine::request(Id id){if(result(s,id)<0)s.text(id,"要求","有効");}
bool Machine::need(Id node,Id dep,Transition& t)const{
    if(dep<0)throw std::runtime_error("入力辺がありません");if(result(s,dep)>=0)return true;
    if(s.text(dep,"要求")!="有効"){t.node=node;t.rule="要求";t.requests.push_back(dep);}return false;
}

// Read one center and its connected inputs. The scheduler chooses which centers
// need inspection; this function never walks the computation space.
std::optional<Transition> Machine::enabled_at(Id id) const {
    const Node& node=s.at(id);
    if(node.port("要求").faces[1].text!="有効"||result(s,id)>=0)return {};
    const auto op=resolve(node.center);
    auto active=roles(op);
    Transition request_t{id,"要求",-1,{},{}},arrival;
    if(active.empty())return Transition{id,"不明な演算",-1,{},{}};
    for(const auto& role:active){
        const auto& a=node.port(role);
        if(a.edges[3].text=="先に要求"&&a.edges[0].ref>=0)need(id,a.edges[0].ref,request_t);
    }
    if(op=="選ぶ"){
        const auto& condition=node.port("条件");
        active={"条件"};
        Id c=condition.vertices[0].ref;
        if(c>=0&&condition.vertices[2].text=="通過"){
            if(s.at(c).center=="失敗")return Transition{id,"結果を接続",-1,{c},{}};
            if(s.at(c).center!="真偽")return Transition{id,"条件の型が違う",-1,{},{}};
            active.push_back(s.text(c,"値")=="真"?"真の枝":"偽の枝");
        }
    }
    if((op=="呼ぶ"||op=="格子へ適用"||op=="格子の分割実行")&&s.ref(id,"展開")>=0)active={"展開"};
    bool waiting=false;
    std::vector<Id> values;
    for(const auto& role:active){
        int p=node.find(role);
        if(p<0){waiting=true;arrival={id,"入力の役割がない",-1,{},{}};break;}
        const auto& a=node.arms[p];
        if(a.vertices[2].text=="閉鎖"){waiting=true;continue;}
        if(a.edges[2].ref>=0){
            if(!need(id,a.edges[2].ref,request_t)){waiting=true;continue;}
            Id gate=result(s,a.edges[2].ref);
            if(s.at(gate).center=="失敗"){arrival={id,"結果を接続",-1,{gate},{}};waiting=true;break;}
            if(s.at(gate).center!="真偽"){arrival={id,"許可条件の型が違う",-1,{},{}};waiting=true;break;}
            if(s.text(gate,"値")=="偽"){arrival={id,"辺を閉じる",p,{gate},{}};waiting=true;continue;}
        }
        if(a.vertices[0].ref>=0&&a.vertices[2].text=="通過"){
            Id v=a.vertices[0].ref;
            if(s.at(v).center=="失敗"){arrival={id,"結果を接続",-1,{v},{}};waiting=true;break;}
            values.push_back(v);
            continue;
        }
        waiting=true;
        Id v=a.vertices[0].ref;
        if(v<0){
            if(a.edges[0].ref<0){arrival={id,"入力辺がない",-1,{},{}};continue;}
            if(!need(id,a.edges[0].ref,request_t))continue;
            v=result(s,a.edges[0].ref);
        }
        if(arrival.node<0)arrival={id,"頂点へ受信",p,{v},{}};
    }
    if(!request_t.requests.empty()){
        std::sort(request_t.requests.begin(),request_t.requests.end());
        request_t.requests.erase(std::unique(request_t.requests.begin(),request_t.requests.end()),request_t.requests.end());
        return request_t;
    }
    if(arrival.node>=0)return arrival;
    if(!waiting&&!(op=="選ぶ"&&active.size()==1)){
        std::string rule="計算";
        if(op=="格子へ分割適用")rule="分割近傍を開始";
        else if(op=="格子の分割実行")rule=active[0]=="展開"?"分割近傍を継続":"分割近傍を展開";
        else if(op=="呼ぶ"||op=="格子へ適用")rule=active[0]=="展開"?"結果を接続":op=="呼ぶ"?"計画を展開":"近傍を展開";
        return Transition{id,rule,-1,values,{}};
    }
    return {};
}
// Retain an exhaustive reference implementation for differential checking.
std::vector<Transition> Machine::enabled() const {
    std::vector<Transition> out;
    for(size_t i=0;i<s.nodes.size();++i)
        if(auto t=enabled_at(static_cast<Id>(i)))out.push_back(std::move(*t));
    return out;
}
Id Machine::compute(const std::string& op,const std::vector<Id>& v){
    if(op=="参照"||op=="選ぶ")return v.back();
    if(op=="足す"||op=="引く"||op=="掛ける"||op=="割る"||op=="以下"){
        if(s.at(v[0]).center!="整数"||s.at(v[1]).center!="整数")throw std::runtime_error("整数二つが必要です");
        int64_t a=std::stoll(s.text(v[0],"値")),b=std::stoll(s.text(v[1],"値")),n=0;bool overflow=false;
        if(op=="以下")return s.boolean(a<=b);
        if(op=="足す")overflow=__builtin_add_overflow(a,b,&n);
        else if(op=="引く")overflow=__builtin_sub_overflow(a,b,&n);
        else if(op=="掛ける")overflow=__builtin_mul_overflow(a,b,&n);
        else {if(b==0)throw std::runtime_error("ゼロでは割れません");if(a==std::numeric_limits<int64_t>::min()&&b==-1)overflow=true;
              else {if(a%b)throw std::runtime_error("整数核では余りのある除算を保留します");n=a/b;}}
        if(overflow)throw std::runtime_error("64ビット整数の範囲を超えました");return s.integer(n);
    }
    if(op=="等しい"){
        for(Id x:v)if(s.at(x).center!="整数"&&s.at(x).center!="文章"&&s.at(x).center!="真偽"&&s.at(x).center!="無")throw std::runtime_error("この値の等価比較は未定義です");
        return s.boolean(s.at(v[0]).center==s.at(v[1]).center&&s.text(v[0],"値")==s.text(v[1],"値"));
    }
    if(op=="つなぐ"){if(s.at(v[0]).center!="文章"||s.at(v[1]).center!="文章")throw std::runtime_error("文章二つが必要です");return s.string(s.text(v[0],"値")+s.text(v[1],"値"));}
    if(op=="対にする"){if(s.at(v[1]).center!="列"&&s.at(v[1]).center!="空列")throw std::runtime_error("右側は列です");Id i=s.add("列");s.link(i,"先頭",v[0]);s.link(i,"残り",v[1]);return i;}
    if(op=="先頭"||op=="残り"||op=="空か"){
        const auto c=s.at(v[0]).center;if(c!="列"&&c!="空列")throw std::runtime_error("列が必要です");
        if(op=="空か")return s.boolean(c=="空列");if(c=="空列")throw std::runtime_error("空列には先頭と残りがありません");return s.ref(v[0],op);
    }
    if(!grid_roles(op).empty())return grid_compute(s,op,v);
    if(!structural_roles(op).empty())return structural_compute(s,op,v);
    throw std::runtime_error("未実装の中心演算です");
}
Id Machine::apply(const Transition& t){
    Id produced=-1;
    if(t.rule=="要求"){for(Id i:t.requests)request(i);}
    else if(t.rule=="辺を閉じる")s.at(t.node).arms[t.port].vertices[2].text="閉鎖";
    else {try{
        if(t.rule=="頂点へ受信"){
            const auto arm=s.at(t.node).arms[t.port];Id value=t.inputs[0];const auto kind=s.at(value).center;
            if(!is_value(kind))throw std::runtime_error("頂点へ届いたものが値ではありません");
            if(kind!="失敗"&&arm.edges[1].text=="型を検査する"){
                const auto type=arm.faces[2].text;bool okay=type.empty()||type=="任意"||kind==type||(type=="列"&&(kind=="列"||kind=="空列"))||(type=="計画"&&kind=="計画の値")||(type=="十字"&&kind=="十字の値")||(type=="格子"&&kind=="格子の値");
                if(!okay)throw std::runtime_error("型の辺を通れません: "+type);
                const auto constraint=arm.faces[3].text;
                if(!constraint.empty()){
                    if(kind!="整数")throw std::runtime_error("符号の制約には整数が必要です");auto n=std::stoll(s.text(value,"値"));
                    if((constraint=="正"&&n<=0)||(constraint=="非負"&&n<0))throw std::runtime_error("値の制約を通れません: "+constraint);
                }
            }
            auto& a=s.at(t.node).arms[t.port];a.vertices[0]={"到着値",value};a.vertices[1]={"接続元",a.edges[0].ref};a.vertices[2].text="通過";a.vertices[3]={"許可の経由",a.edges[2].ref};
        }else if(t.rule=="結果を接続")produced=t.inputs[0];
        else if(t.rule=="分割近傍を開始"){
            start_grid_chunks(s,t.node,t.inputs[0],t.inputs[1],t.inputs[2]);
        }else if(t.rule=="分割近傍を展開"){
            Id body=expand_grid_chunk(s,t.inputs[0],t.inputs[1],t.inputs[2]);s.link(t.node,"展開",body);
        }else if(t.rule=="分割近傍を継続"){
            produced=advance_grid_chunk(s,t.node,t.inputs[0]);
        }else if(t.rule=="近傍を展開"){
            Id body=expand_grid(s,t.inputs[0],t.inputs[1]);s.link(t.node,"展開",body);
        }else if(t.rule=="計画を展開"){
            if(s.at(t.inputs[0]).center!="計画の値")throw std::runtime_error("呼び出しには計画の値が必要です");
            Id definition=s.ref(t.inputs[0],"定義");if(s.at(definition).center!="計画")throw std::runtime_error("計画定義がありません");
            Id body=instantiate(s,s.ref(definition,"本文"),{{s.ref(definition,"引数"),t.inputs[1]}});s.link(t.node,"展開",body);
        }else if(t.rule=="計算")produced=compute(resolve(s.at(t.node).center),t.inputs);
        else throw std::runtime_error(t.rule);
    }catch(const BudgetError&){throw;}catch(const std::exception& e){produced=s.error(e.what());}
    if(produced>=0)s.at(t.node).port("結果").vertices[0]={"結果値",produced};}
    Id event=s.add("局所変化");s.text(event,"規則",t.rule);s.link(event,"対象",t.node);if(produced>=0)s.link(event,"生成値",produced);
    if(!t.inputs.empty()){Id bundle=s.sequence(t.inputs);s.link(event,"入力値",bundle);}return event;
}
Report Machine::run(const std::string& policy,size_t maximum,uint64_t seed,const std::string& scheduler){
    if(policy!="batch"&&policy!="forward"&&policy!="reverse"&&policy!="random")throw std::runtime_error("未知の実行順です");
    if(scheduler!="events"&&scheduler!="scan")throw std::runtime_error("未知のスケジューラです");
    request(output());Report report;report.peak_nodes=s.nodes.size();report.scheduler=scheduler;report.status="STEP_BUDGET";std::mt19937_64 rng(seed);
    // This index is a disposable host cache, reconstructed from the image at
    // each run. The Node state alone determines every enabled transition.
    std::vector<std::set<Id>> consumers;
    std::set<Id> dirty;
    std::map<Id,Transition> ready;
    size_t indexed=0;
    const auto subscribe=[&](Id id){
        const auto& node=s.at(id);
        auto inputs=roles(resolve(node.center));
        if(inputs.empty())return;
        if(s.ref(id,"展開")>=0)inputs.push_back("展開");
        for(const auto& role:inputs){
            const auto& a=node.port(role);
            for(Id dep:{a.edges[0].ref,a.edges[2].ref})
                if(dep>=0)consumers.at(static_cast<size_t>(dep)).insert(id);
        }
    };
    const auto index_new=[&]{
        consumers.resize(s.nodes.size());
        for(;indexed<s.nodes.size();++indexed){
            ++report.index_nodes;
            Id id=static_cast<Id>(indexed);
            subscribe(id);
            if(s.text(id,"要求")=="有効")dirty.insert(id);
        }
    };
    const auto changed=[&](Id id){
        dirty.insert(id);
        for(Id consumer:consumers.at(static_cast<size_t>(id)))dirty.insert(consumer);
    };
    if(scheduler=="events")index_new();
    for(size_t step=0;step<maximum&&result(s,output())<0;++step){
        std::vector<Transition> ts;
        if(scheduler=="scan"){
            report.node_inspections+=s.nodes.size();
            ts=enabled();
        }else{
            for(Id id:dirty){
                ++report.node_inspections;
                if(auto t=enabled_at(id))ready[id]=std::move(*t);
                else ready.erase(id);
            }
            dirty.clear();
            for(const auto& entry:ready)ts.push_back(entry.second);
        }
        if(ts.empty()){
            report.status="STUCK";for(const auto& n:s.nodes)if(n.port("要求").faces[1].text=="有効")for(const auto& a:n.arms)if(a.vertices[2].text=="閉鎖")report.status="BLOCKED";break;
        }
        report.max_enabled=std::max(report.max_enabled,ts.size());size_t width=ts.size();
        if(policy=="forward")ts={ts.front()};else if(policy=="reverse")ts={ts.back()};else if(policy=="random")ts={ts[std::uniform_int_distribution<size_t>(0,ts.size()-1)(rng)]};
        // All transitions were selected from one pre-state. Shared demand flags
        // are monotone. A batch does not observe values produced within itself.
        const size_t before=s.nodes.size();std::map<Id,Node> original;original[s.root]=s.at(s.root);
        for(const auto& t:ts){original[t.node]=s.at(t.node);for(Id i:t.requests)original[i]=s.at(i);}
        try{
            std::vector<Id> events;for(const auto& t:ts)events.push_back(apply(t));Id bundle=s.sequence(events),history=s.add("観測した段階");
            s.link(history,"変化",bundle);Id previous=s.ref(s.root,"履歴");if(previous>=0)s.link(history,"前の観測",previous);
            s.text(history,"選び方",policy);s.text(history,"同時に有効",std::to_string(width));s.link(s.root,"履歴",history);
        }catch(const BudgetError&){report.peak_nodes=std::max(report.peak_nodes,s.nodes.size());s.nodes.resize(before);for(auto& [id,n]:original)s.at(id)=std::move(n);report.status="NODE_BUDGET";break;}
        for(const auto& t:ts)if(t.rule=="近傍を展開"&&s.ref(t.node,"展開")>=0){
            ++report.grid_expansions;
            auto cells=grid_cells(s,t.inputs[0]).size();report.expanded_cells+=cells;report.neighbor_slots+=6*cells;
        }
        for(const auto& t:ts){
            if(t.rule=="分割近傍を開始"&&s.at(t.node).center=="格子の分割実行")++report.grid_expansions;
            if(t.rule=="分割近傍を展開"&&s.ref(t.node,"展開")>=0){
                size_t count=grid_chunk_size(s,t.inputs[2]);++report.grid_chunks;
                report.expanded_cells+=count;report.neighbor_slots+=6*count;report.max_chunk_cells=std::max(report.max_chunk_cells,count);
            }
        }
        if(scheduler=="events"){
            index_new();
            for(const auto& t:ts){
                // Expansion adds a dependency to an existing call center.
                if(t.rule=="計画を展開"||t.rule=="近傍を展開"||t.rule=="分割近傍を開始"||t.rule=="分割近傍を展開"||t.rule=="分割近傍を継続")subscribe(t.node);
                changed(t.node);
                for(Id id:t.requests)changed(id);
            }
        }
        ++report.steps;report.transitions+=ts.size();
    }
    report.peak_nodes=std::max(report.peak_nodes,s.nodes.size());report.value=result(s,output());if(report.value>=0)report.status=s.at(report.value).center=="失敗"?"ERROR":"COMPLETE";return report;
}
std::string report_json(const Space& s,const Report& r){
    std::ostringstream out;out<<"{\"status\":"<<quote_json(r.status)<<",\"value\":"<<(r.value>=0?export_json(s,r.value):"null")
        <<",\"steps\":"<<r.steps<<",\"local_transitions\":"<<r.transitions<<",\"max_enabled\":"<<r.max_enabled
        <<",\"scheduler\":"<<quote_json(r.scheduler)<<",\"node_inspections\":"<<r.node_inspections<<",\"index_nodes\":"<<r.index_nodes
        <<",\"nodes\":"<<s.nodes.size()<<",\"memory_policy\":"<<quote_json(r.memory_policy)
        <<",\"collections\":"<<r.collections<<",\"reclaimed_nodes\":"<<r.reclaimed_nodes<<",\"peak_nodes\":"<<r.peak_nodes
        <<",\"grid_expansions\":"<<r.grid_expansions<<",\"expanded_cells\":"<<r.expanded_cells<<",\"neighbor_slots\":"<<r.neighbor_slots
        <<",\"grid_chunks\":"<<r.grid_chunks<<",\"max_chunk_cells\":"<<r.max_chunk_cells
        <<",\"program_counter\":null,\"host_parallel_execution\":false}";return out.str();
}
}
