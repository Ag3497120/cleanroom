#include "cross.hpp"
#include <algorithm>
#include <functional>
#include <regex>
#include <sstream>

namespace cross {
namespace {
const std::string A=R"((?:数「-?[0-9]+」|文「.*?」|計画「.+?」|「.+?」|真|偽|無|空の列|入力))";
bool match(const std::string& line,const std::string& pattern,std::smatch& m){return std::regex_match(line,m,std::regex(pattern));}
std::string trim(const std::string& s){auto b=s.find_first_not_of(" \t\r\n");return b==std::string::npos?"":s.substr(b,s.find_last_not_of(" \t\r\n")-b+1);}
struct Line {size_t number;std::string name,expression,raw;bool structural=false;};
struct Block {std::string name,parameter,output;Id definition=-1,param=-1;std::vector<Line> lines;std::map<std::string,Id> symbols;};
struct Binding {std::string role,value,type;bool capture;};
struct Pattern {std::string surface,kind,target,regex;std::vector<std::string> captures;std::vector<Binding> bindings;};
int index_of(const std::string& word,const std::vector<std::string>& choices){auto i=std::find(choices.begin(),choices.end(),word);if(i==choices.end())throw std::runtime_error("未知の場所: "+word);return static_cast<int>(i-choices.begin());}
void prepare_input(Space& s,Id node,const std::string& role,Id value,const std::string& type="任意"){
    s.link(node,role,value);auto& arm=s.at(node).port(role);arm.faces[2].text=type;arm.edges[1].text="型を検査する";arm.edges[3].text="必要時だけ";
}
void contract(Space& s,Id node,const std::string& role,const std::string& type){
    auto& a=s.at(node).port(role);a.edges[1].text="型を検査する";
    if(type=="正の整数"||type=="非負の整数"){a.faces[2].text="整数";a.faces[3].text=type=="正の整数"?"正":"非負";}
    else {index_of(type,{"任意","整数","文章","真偽","列","計画","記録","十字","格子"});a.faces[2].text=type;}
}
Pattern pattern(const std::string& surface,const std::string& kind,const std::string& target,const std::string& assignments){
    Pattern p{surface,kind,target,"",{}, {}};std::set<std::string> names;
    for(size_t i=0;i<surface.size();){
        if(surface[i]=='{'){auto end=surface.find('}',i+1);if(end==std::string::npos||end==i+1)throw std::runtime_error("パターンの捕捉名が不正です");
            auto name=surface.substr(i+1,end-i-1);if(!names.insert(name).second)throw std::runtime_error("捕捉名は一回だけ記述してください。同値は等しい構造で検査します");
            p.captures.push_back(name);p.regex+="("+A+")";i=end+1;
        }else{char c=surface[i++];if(c=='}')throw std::runtime_error("余分な閉じ波括弧です");if(std::string(".^$|()[]*+?\\").find(c)!=std::string::npos)p.regex+='\\';p.regex+=c;}
    }
    std::string literal=surface;for(const auto& n:p.captures){auto pos=literal.find("{"+n+"}");literal.erase(pos,n.size()+2);}
    if(trim(literal).empty())throw std::runtime_error("意味パターンには区別できる表現が必要です");
    std::set<std::string> assigned,used;size_t start=0;
    while(start<assignments.size()){
        size_t end=std::string::npos;int quoted=0;
        for(size_t j=start;j<assignments.size();){
            if(assignments.compare(j,3,"「")==0){++quoted;j+=3;}
            else if(assignments.compare(j,3,"」")==0){--quoted;j+=3;}
            else if(quoted==0&&assignments.compare(j,3,"、")==0){end=j;break;}
            else ++j;
        }
        auto item=assignments.substr(start,end==std::string::npos?std::string::npos:end-start);std::smatch m;
        if(!match(item,"\\s*(.+?)\\s*(?:＝|=)\\s*(\\{[^{}]+\\}|"+A+")\\s*(?::|：)\\s*(.+?)\\s*",m))throw std::runtime_error("意味束縛は 役割＝{捕捉名}:型 で指定してください");
        std::string role=trim(m[1]),value=trim(m[2]),type=trim(m[3]);bool capture=value.front()=='{';
        if(!assigned.insert(role).second)throw std::runtime_error("入力役割の束縛が重複しています");
        if(capture){value=value.substr(1,value.size()-2);if(!names.count(value))throw std::runtime_error("未捕捉の名前を束縛しています");used.insert(value);}
        index_of(type,{"任意","整数","正の整数","非負の整数","文章","真偽","列","計画","記録","十字","格子"});p.bindings.push_back({role,value,type,capture});
        if(end==std::string::npos)break;start=end+3;
    }
    if(used!=names)throw std::runtime_error("意味に使われない捕捉があります");return p;
}
}

Space compile(const std::string& source,const std::string& input,size_t limit){
    if(source.size()>1024*1024)throw std::runtime_error("参照コンパイラのソース上限は1MiBです");
    validate_utf8(source);
    std::map<std::string,Block> blocks;blocks["主計画"].name="主計画";std::string current="主計画",project="立体十字の計画";
    std::map<std::string,std::string> aliases;std::vector<Pattern> patterns;std::istringstream stream(source);std::string raw;size_t number=0;
    while(std::getline(stream,raw)){
        ++number;std::string line=trim(raw);if(line.empty()||line[0]=='#')continue;
        if(line.size()<3||line.substr(line.size()-3)!="。")throw std::runtime_error(std::to_string(number)+"行: 文末の「。」が必要です");
        line.resize(line.size()-3);std::smatch m;
        if(match(line,"計画「(.+?)」は「(.+?)」を受け取る",m)){
            if(current!="主計画"||blocks.count(m[1]))throw std::runtime_error("計画の重複または入れ子宣言です");
            current=m[1];blocks[current].name=current;blocks[current].parameter=m[2];
        }else if(line=="計画を終える"){
            if(current=="主計画"||blocks[current].output.empty())throw std::runtime_error("返す値を指定して計画を閉じてください");current="主計画";
        }else if(match(line,"返すのは("+A+")",m)){
            if(current=="主計画"||!blocks[current].output.empty())throw std::runtime_error("返す値は一つです");blocks[current].output=m[1];
        }else if(match(line,"出力は("+A+")",m)){
            if(current!="主計画"||!blocks[current].output.empty())throw std::runtime_error("主計画の出力は一つです");blocks[current].output=m[1];
        }else if(match(line,"プロジェクト「(.+?)」",m)){project=m[1];
        }else if(match(line,"意味「(.*?)」\\s*(?:＝|=)\\s*(中心|計画)「(.+?)」（(.+)）",m)){
            if(current!="主計画")throw std::runtime_error("意味パターンはプロジェクトの領域で定義してください");
            patterns.push_back(pattern(m[1],m[2],m[3],m[4]));
        }else if(match(line,"言葉「(.+?)」は動き「(.+?)」を表す",m)){
            if(current!="主計画"||aliases.count(m[1])||!roles(m[1]).empty()||roles(m[2]).empty())throw std::runtime_error("語義は既知の演算へ一意に結び付けてください");aliases[m[1]]=m[2];
        }else if(match(line,"十字「(.+?)」の中心は「(.+?)」",m)){
            blocks[current].lines.push_back({number,m[1],m[2],line,true});
        }else if(line.rfind("十字「",0)==0){
            blocks[current].lines.push_back({number,"","",line,true});
        }else if(match(line,"「(.+?)」は(.+)",m)){
            blocks[current].lines.push_back({number,m[1],m[2],line,false});
        }else throw std::runtime_error(std::to_string(number)+"行: 未定義の文型です: "+line);
    }
    if(current!="主計画"||blocks["主計画"].output.empty())throw std::runtime_error("計画を閉じて主計画の出力を指定してください");
    Space s;s.limit=limit;s.root=s.add("計算空間");Id imported=import_json(s,input);s.link(s.root,"資料",imported);
    Id source_id=s.string(source);s.link(s.root,"原文",source_id);
    std::vector<Id> meanings;
    for(const auto& [word,op]:aliases){Id i=s.add("語義");s.text(i,"表現",word);s.text(i,"動き",op);meanings.push_back(i);}
    for(const auto& p:patterns){
        std::set<std::string> assigned;for(const auto& b:p.bindings)assigned.insert(b.role);
        auto required=p.kind=="計画"?std::vector<std::string>{"入力"}:roles(aliases.count(p.target)?aliases.at(p.target):p.target);
        if(required.empty()||assigned!=std::set<std::string>(required.begin(),required.end()))throw std::runtime_error("意味パターンが中心の必要な入力を満たしていません: "+p.surface);
        if(p.kind=="計画"&&(!blocks.count(p.target)||p.target=="主計画"))throw std::runtime_error("意味パターンの計画がありません");
        std::vector<Id> bound;for(const auto& b:p.bindings){Id i=s.add("意味束縛");s.text(i,"役割",b.role);s.text(i,"値の表現",b.value);s.text(i,"型",b.type);s.text(i,"参照方式",b.capture?"捕捉":"即値");bound.push_back(i);}
        Id bundle=s.sequence(bound),i=s.add("意味パターン");s.text(i,"表現",p.surface);s.text(i,"構造種",p.kind);s.text(i,"構造名",p.target);s.link(i,"束縛",bundle);meanings.push_back(i);
    }
    Id meaning_root=s.sequence(meanings);s.link(s.root,"規則集",meaning_root);
    for(auto& [name,b]:blocks){
        b.param=s.add("引数");s.text(b.param,"名前",b.parameter.empty()?"入力":b.parameter);
        b.definition=s.add("計画");s.text(b.definition,"名前",name=="主計画"?project:name);s.link(b.definition,"引数",b.param);
        if(!b.parameter.empty())b.symbols[b.parameter]=b.param;
        for(const auto& line:b.lines)if(!line.name.empty()){
            if(b.symbols.count(line.name))throw std::runtime_error(std::to_string(line.number)+"行: 名前が重複しています: "+line.name);
            const std::string center=line.structural?line.expression:"参照";
            if(roles(operation(s,center)).empty())throw std::runtime_error("未知の中心演算: "+center);
            b.symbols[line.name]=s.add(center);
        }
    }
    std::function<Id(const std::string&,Block&)> atom=[&](const std::string& t,Block& b)->Id{
        std::smatch m;
        if(match(t,"数「(-?[0-9]+)」",m)){size_t used;auto v=std::stoll(m[1],&used);if(used!=static_cast<size_t>(m[1].length()))throw std::runtime_error("数が不正です");return s.integer(v);}
        if(match(t,"文「(.*?)」",m))return s.string(m[1]);
        if(match(t,"計画「(.+?)」",m)){if(!blocks.count(m[1])||m[1]=="主計画")throw std::runtime_error("未定義の計画です");Id i=s.add("計画の値");s.link(i,"定義",blocks[m[1]].definition);return i;}
        if(match(t,"「(.+?)」",m)){if(!b.symbols.count(m[1]))throw std::runtime_error("未定義の名前: "+m[1].str());return b.symbols[m[1]];}
        if(t=="入力")return b.name=="主計画"?imported:b.param;
        if(t=="真"||t=="偽")return s.boolean(t=="真");
        if(t=="無")return s.add("無");if(t=="空の列")return s.add("空列");
        throw std::runtime_error("値の記述が不明です: "+t);
    };
    auto binary=[&](const std::string& center,Id a,Id b)->Id{Id n=s.add(center);std::string op=operation(s,center);std::string type=(op=="足す"||op=="引く"||op=="掛ける"||op=="割る"||op=="以下")?"整数":op=="つなぐ"?"文章":"任意";prepare_input(s,n,"左",a,type);prepare_input(s,n,"右",b,type);return n;};
    auto builtin_expression=[&](const std::string& t,Block& b)->Id{
        std::smatch m;if(match(t,A,m))return atom(t,b);
        if(match(t,"("+A+")と("+A+")を(.+)",m)){
            std::string op=operation(s,m[3]);if(op!="足す"&&op!="掛ける"&&op!="つなぐ"&&op!="対にする")throw std::runtime_error("この二項構文で使えない動きです");return binary(m[3],atom(m[1],b),atom(m[2],b));
        }
        for(const auto& [pattern,op]:std::vector<std::pair<std::string,std::string>>{
            {"("+A+")から("+A+")を引く","引く"},{"("+A+")を("+A+")で割る","割る"},
            {"("+A+")が("+A+")以下か","以下"},{"("+A+")と("+A+")が等しいか","等しい"}})
            if(match(t,pattern,m))return binary(op,atom(m[1],b),atom(m[2],b));
        if(match(t,"("+A+")(の先頭|の残り|が空か)",m)){std::string op=m[2].str().substr(3);Id n=s.add(op);prepare_input(s,n,"値",atom(m[1],b),"列");return n;}
        if(match(t,"("+A+")なら("+A+")、そうでなければ("+A+")を選ぶ",m)){
            Id n=s.add("選ぶ");prepare_input(s,n,"条件",atom(m[1],b),"真偽");prepare_input(s,n,"真の枝",atom(m[2],b));prepare_input(s,n,"偽の枝",atom(m[3],b));return n;
        }
        if(match(t,"("+A+")に("+A+")を渡す",m)){Id n=s.add("呼ぶ");prepare_input(s,n,"計画",atom(m[1],b),"計画");prepare_input(s,n,"入力",atom(m[2],b));return n;}
        throw std::runtime_error("計算文を一意に解釈できません: "+t);
    };
    auto expression=[&](const std::string& t,Block& b)->Id{
        std::vector<std::pair<const Pattern*,std::map<std::string,std::string>>> candidates;
        for(const auto& p:patterns){std::smatch m;if(!match(t,p.regex,m))continue;std::map<std::string,std::string> captures;for(size_t i=0;i<p.captures.size();++i)captures[p.captures[i]]=m[i+1];candidates.push_back({&p,std::move(captures)});}
        std::smatch m;bool builtin=match(t,A,m);
        for(const auto& form:std::vector<std::string>{"("+A+")から("+A+")を引く","("+A+")を("+A+")で割る","("+A+")が("+A+")以下か","("+A+")と("+A+")が等しいか","("+A+")(の先頭|の残り|が空か)","("+A+")なら("+A+")、そうでなければ("+A+")を選ぶ","("+A+")に("+A+")を渡す"})builtin|=match(t,form,m);
        if(match(t,"("+A+")と("+A+")を(.+)",m)){auto op=operation(s,m[3]);builtin|=op=="足す"||op=="掛ける"||op=="つなぐ"||op=="対にする";}
        if(candidates.size()+(builtin?1:0)>1)throw std::runtime_error("AMBIGUOUS_MEANING: 複数の意味パターンに一致します: "+t);
        if(builtin)return builtin_expression(t,b);
        if(candidates.empty())throw std::runtime_error("UNDEFINED_MEANING: 対応する意味パターンがありません: "+t);
        const auto& p=*candidates[0].first;const auto& captures=candidates[0].second;Id n=s.add(p.kind=="計画"?"呼ぶ":p.target);
        if(p.kind=="計画"){Id value=s.add("計画の値");s.link(value,"定義",blocks.at(p.target).definition);prepare_input(s,n,"計画",value,"計画");}
        for(const auto& binding:p.bindings){Id value=atom(binding.capture?captures.at(binding.value):binding.value,b);prepare_input(s,n,binding.role,value);contract(s,n,binding.role,binding.type);}
        return n;
    };
    for(auto& [name,b]:blocks){
        for(const auto& line:b.lines){try{
            if(!line.structural){prepare_input(s,b.symbols.at(line.name),"対象",expression(line.expression,b));continue;}
            if(!line.name.empty())continue;
            std::smatch m;
            if(!match(line.raw,"十字「(.+?)」の腕「(.+?)」の(面|辺|頂点)「(.+?)」は(.+)",m))throw std::runtime_error("面・辺・頂点の構文が不正です");
            if(!b.symbols.count(m[1]))throw std::runtime_error("未定義の十字です");Id n=b.symbols.at(m[1]);
            int arm=index_of(m[2],{"+x","-x","+y","-y","+z","-z"});std::string site=m[3],place=m[4],rhs=m[5];
            std::smatch payload;
            if(site=="面"){
                int face=index_of(place,{"北","南","東","西"});
                if(!match(rhs,"「(.*?)」",payload))throw std::runtime_error("面の内容は「…」で指定してください");
                s.at(n).arms[arm].faces[face].text=payload[1];
            }else if(site=="辺"){
                int edge=index_of(place,{"北東","南東","南西","北西"});
                if(edge==0&&match(rhs,"("+A+")から受け取る",payload)){Id v=atom(payload[1],b);s.at(n).arms[arm].edges[edge]={"受け取る",v};}
                else if(edge==1&&rhs=="型を検査する")s.at(n).arms[arm].edges[edge].text=rhs;
                else if(edge==2&&match(rhs,"("+A+")なら開く",payload)){Id v=atom(payload[1],b);s.at(n).arms[arm].edges[edge]={"許可時",v};}
                else if(edge==3&&(rhs=="必要時だけ"||rhs=="先に要求"))s.at(n).arms[arm].edges[edge].text=rhs;
                else throw std::runtime_error("この辺に定義されていない関係です");
            }else{
                int vertex=index_of(place,{"北東端","南東端","南西端","北西端"});
                if(vertex!=0)throw std::runtime_error("南東端・南西端・北西端は実行器が記録する頂点です");
                Id v=atom(rhs,b);if(!is_value(s.at(v).center))throw std::runtime_error("初期頂点には即値を置いてください");s.at(n).arms[arm].vertices[0]={"初期値",v};
            }
        }catch(const std::exception& e){throw std::runtime_error(std::to_string(line.number)+"行: "+e.what());}}
        Id body=atom(b.output,b);s.link(b.definition,"本文",body);
    }
    // Explicit structure must be executable, not merely a drawing with labels.
    for(size_t i=0;i<s.nodes.size();++i){
        const auto node=s.nodes[i];auto required=roles(operation(s,node.center));if(required.empty())continue;
        for(const auto& role:required){
            int p=node.find(role);if(p<0)throw std::runtime_error("必要な面の役割がありません: "+node.center+" / "+role);
            const auto& a=node.arms[p];if(a.edges[0].ref<0&&a.vertices[0].ref<0)throw std::runtime_error("入力辺または初期頂点が必要です: "+role);
            if(a.edges[0].ref>=0&&a.vertices[0].ref>=0)throw std::runtime_error("入力辺と初期頂点の二重指定です");
            if((!a.faces[2].text.empty()||!a.faces[3].text.empty())&&a.edges[1].text!="型を検査する")throw std::runtime_error("型・制約の面には検査辺が必要です");
            if(!a.faces[2].text.empty())index_of(a.faces[2].text,{"任意","整数","文章","真偽","列","計画","記録","十字","格子"});
            if(!a.faces[3].text.empty())index_of(a.faces[3].text,{"正","非負"});
        }
        for(const auto& a:node.arms)if(!a.faces[0].text.empty()&&std::find(required.begin(),required.end(),a.faces[0].text)==required.end())throw std::runtime_error("演算にない腕の役割です: "+a.faces[0].text);
    }
    std::vector<Id> definitions;for(const auto& [name,b]:blocks)definitions.push_back(b.definition);
    Id registry=s.sequence(definitions);s.link(s.root,"定義集",registry);
    auto& main=blocks["主計画"];Id entry=instantiate(s,s.ref(main.definition,"本文"),{{main.param,imported}});s.link(s.root,"実行",entry);
    s.validate();return s;
}
}
