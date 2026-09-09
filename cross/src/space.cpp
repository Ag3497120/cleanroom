#include "cross.hpp"
#include <algorithm>
#include <fstream>
#include <functional>
#include <iomanip>
#include <limits>
#include <sstream>
#include <cstdio>
#include <regex>

namespace cross {
int Node::find(const std::string& role) const {
    for (int i = 0; i < 6; ++i) if (arms[i].faces[0].text == role) return i;
    return -1;
}
Arm& Node::port(const std::string& role) {
    int i = find(role);
    if (i >= 0) return arms[i];
    for (auto& a : arms) if (a.faces[0].text.empty()) { a.faces[0].text = role; return a; }
    throw std::runtime_error("六腕の容量を超えました");
}
const Arm& Node::port(const std::string& role) const {
    int i = find(role);
    static const Arm empty;
    return i >= 0 ? arms[i] : empty;
}
Id Space::add(const std::string& center) {
    if (nodes.size() >= limit || nodes.size() >= static_cast<size_t>(std::numeric_limits<Id>::max()))
        throw BudgetError("ノード予算に到達しました");
    nodes.push_back(Node{center, {}});
    return static_cast<Id>(nodes.size() - 1);
}
Node& Space::at(Id i) { if (i < 0) throw std::runtime_error("接続先がありません"); return nodes.at(static_cast<size_t>(i)); }
const Node& Space::at(Id i) const { if (i < 0) throw std::runtime_error("接続先がありません"); return nodes.at(static_cast<size_t>(i)); }
void Space::link(Id n, const std::string& role, Id v) { auto& a = at(n).port(role); a.edges[0] = {"受け取る", v}; }
Id Space::ref(Id n, const std::string& role) const { return at(n).port(role).edges[0].ref; }
void Space::text(Id n, const std::string& role, const std::string& v) { at(n).port(role).faces[1].text = v; }
std::string Space::text(Id n, const std::string& role) const { return at(n).port(role).faces[1].text; }
Id Space::integer(int64_t n) { Id i = add("整数"); text(i,"値",std::to_string(n)); return i; }
Id Space::boolean(bool b) { Id i = add("真偽"); text(i,"値",b ? "真" : "偽"); return i; }
Id Space::string(const std::string& v) { Id i = add("文章"); text(i,"値",v); return i; }
Id Space::error(const std::string& v) { Id i = add("失敗"); text(i,"理由",v); return i; }
Id Space::sequence(const std::vector<Id>& values) {
    if (values.empty()) return add("空の束");
    std::vector<Id> level;
    for (size_t i = 0; i < values.size(); i += 6) {
        Id page = add("束の葉");
        for (size_t j = i; j < std::min(i+6,values.size()); ++j) link(page,std::to_string(j-i),values[j]);
        level.push_back(page);
    }
    while (level.size() > 1) {
        std::vector<Id> upper;
        for (size_t i=0; i<level.size(); i+=6) {
            Id page = add("束の枝");
            for (size_t j=i; j<std::min(i+6,level.size()); ++j) link(page,std::to_string(j-i),level[j]);
            upper.push_back(page);
        }
        level = std::move(upper);
    }
    return level[0];
}
std::vector<Id> Space::items(Id root_id) const {
    std::vector<Id> pending{root_id}, out; std::set<Id> visited;
    while (!pending.empty()) {
        Id i=pending.back(); pending.pop_back();
        if (!visited.insert(i).second) throw std::runtime_error("束が循環しています");
        const auto& node=at(i);
        if (node.center=="空の束") continue;
        if (node.center=="束の葉") { for(int j=0;j<6;++j) if(ref(i,std::to_string(j))>=0) out.push_back(ref(i,std::to_string(j))); }
        else if (node.center=="束の枝") { for(int j=5;j>=0;--j) if(ref(i,std::to_string(j))>=0) pending.push_back(ref(i,std::to_string(j))); }
        else throw std::runtime_error("束ではありません");
    }
    return out;
}
void Space::validate() const {
    at(root);
    for (const auto& n:nodes) {
        validate_utf8(n.center);
        if(n.center.empty()) throw std::runtime_error("中心語が空です");
        std::set<std::string> names;
        for(const auto& a:n.arms) {
            if(!a.faces[0].text.empty() && !names.insert(a.faces[0].text).second) throw std::runtime_error("腕の役割が重複しています");
            for(const auto* sites:{&a.faces,&a.edges,&a.vertices}) for(const auto& p:*sites) {
                validate_utf8(p.text);
                if(p.ref < -1 || (p.ref>=0 && static_cast<size_t>(p.ref)>=nodes.size())) throw std::runtime_error("参照先が壊れています");
            }
        }
    }
    // A snapshot is also an input format. Pointer bounds alone cannot validate
    // the values that arithmetic and JSON export subsequently trust.
    const auto require_kind=[&](Id id,const std::string& kind){
        if(at(id).center!=kind)throw std::runtime_error("保存状態の型が違います: "+kind);
    };
    std::map<std::string,std::string> aliases;
    if(at(root).center=="計算空間"){
        at(ref(root,"実行"));
        Id registry=ref(root,"規則集");
        if(registry>=0)for(Id id:items(registry))if(at(id).center=="語義"){
            auto name=text(id,"表現"),op=text(id,"動き");
            if(name.empty()||!roles(name).empty()||roles(op).empty()||!aliases.emplace(name,op).second)
                throw std::runtime_error("保存状態の語義が不正です");
        }
    }else if(at(root).center=="資料空間"){
        if(!is_value(at(ref(root,"資料")).center))throw std::runtime_error("資料が値ではありません");
    }
    static const std::regex decimal(R"(-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?)");
    for(size_t i=0;i<nodes.size();++i){
        Id id=static_cast<Id>(i);
        const auto& n=nodes[i];
        if(n.center=="整数"){
            const auto value=text(id,"値");size_t used=0;
            auto parsed=std::stoll(value,&used);
            if(used!=value.size()||std::to_string(parsed)!=value)throw std::runtime_error("保存状態の整数が不正です");
        }else if(n.center=="小数"){
            const auto value=text(id,"値");
            if(value.find_first_of(".eE")==std::string::npos||!std::regex_match(value,decimal))
                throw std::runtime_error("保存状態の小数が不正です");
        }else if(n.center=="真偽"){
            if(text(id,"値")!="真"&&text(id,"値")!="偽")throw std::runtime_error("保存状態の真偽値が不正です");
        }else if(n.center=="列"){
            if(!is_value(at(ref(id,"先頭")).center))throw std::runtime_error("列の先頭が値ではありません");
            const auto tail=at(ref(id,"残り")).center;
            if(tail!="列"&&tail!="空列")throw std::runtime_error("列の末尾が不正です");
        }else if(n.center=="十字の値")validate_structural_value(*this,id);
        else if(n.center=="格子の値"||n.center=="セル束"||n.center=="格子の進行")validate_grid_value(*this,id);
        else if(n.center=="計画の値")require_kind(ref(id,"定義"),"計画");
        else if(n.center=="計画"){
            require_kind(ref(id,"引数"),"引数");at(ref(id,"本文"));
        }else if(n.center=="記録"){
            std::set<std::string> names;
            for(Id entry:items(ref(id,"内容"))){
                require_kind(entry,"項目");require_kind(ref(entry,"名前"),"文章");
                if(!names.insert(text(ref(entry,"名前"),"値")).second||!is_value(at(ref(entry,"値")).center))
                    throw std::runtime_error("記録の項目が不正です");
            }
        }
        auto op=aliases.count(n.center)?aliases.at(n.center):n.center;
        const auto inputs=roles(op);
        const auto demand=text(id,"要求");
        Id completed=n.port("結果").vertices[0].ref;
        if(!demand.empty()&&demand!="有効")throw std::runtime_error("要求状態が不正です");
        if(completed>=0&&!is_value(at(completed).center))throw std::runtime_error("結果が値ではありません");
        if(inputs.empty()){
            if(!is_value(n.center)&&(!demand.empty()||completed>=0))throw std::runtime_error("実行状態を持つ未知の中心です");
            continue;
        }
        auto required=inputs;
        if(ref(id,"展開")>=0){
            if(op!="呼ぶ"&&op!="格子へ適用"&&op!="格子の分割実行")throw std::runtime_error("計画呼出し以外に展開があります");
            required.push_back("展開");
        }
        for(const auto& role:required){
            const auto& a=n.port(role);
            if(n.find(role)<0||(a.edges[0].ref<0&&a.vertices[0].ref<0))throw std::runtime_error("保存状態の入力がありません: "+role);
            if(a.vertices[0].ref>=0&&!is_value(at(a.vertices[0].ref).center))throw std::runtime_error("到着値が値ではありません");
            auto state=a.vertices[2].text;
            if((state!=""&&state!="通過"&&state!="閉鎖")||(state=="通過"&&a.vertices[0].ref<0))throw std::runtime_error("頂点の検査状態が不正です");
            const auto type=a.faces[2].text,constraint=a.faces[3].text;
            if((!type.empty()||!constraint.empty())&&a.edges[1].text!="型を検査する")throw std::runtime_error("型検査辺がありません");
            if(type!=""&&type!="任意"&&type!="整数"&&type!="文章"&&type!="真偽"&&type!="列"&&type!="計画"&&type!="記録"&&type!="十字"&&type!="格子")throw std::runtime_error("型の面が不正です");
            if(constraint!=""&&constraint!="正"&&constraint!="非負")throw std::runtime_error("制約の面が不正です");
            if(state=="通過"&&at(a.vertices[0].ref).center!="失敗"){
                const auto kind=at(a.vertices[0].ref).center;
                if(!type.empty()&&type!="任意"&&kind!=type&&!(type=="列"&&kind=="空列")&&!(type=="計画"&&kind=="計画の値")&&!(type=="十字"&&kind=="十字の値")&&!(type=="格子"&&kind=="格子の値"))
                    throw std::runtime_error("型に違反する通過済み頂点です");
                if(!constraint.empty()){
                    require_kind(a.vertices[0].ref,"整数");auto value=std::stoll(text(a.vertices[0].ref,"値"));
                    if((constraint=="正"&&value<=0)||(constraint=="非負"&&value<0))throw std::runtime_error("制約に違反する通過済み頂点です");
                }
            }
        }
    }
    for(size_t i=0;i<nodes.size();++i) {
        Id id=static_cast<Id>(i);const auto& n=nodes[i];
        if(n.center=="観測した段階") {
            const auto width=text(id,"同時に有効");size_t used=0;auto count=std::stoull(width,&used);
            if(count==0||used!=width.size()||std::to_string(count)!=width)throw std::runtime_error("履歴の有効数が不正です");
            auto policy=text(id,"選び方");if(policy!="batch"&&policy!="forward"&&policy!="reverse"&&policy!="random")throw std::runtime_error("履歴の選び方が不正です");
            for(Id event:items(ref(id,"変化")))require_kind(event,"局所変化");
            if(ref(id,"前の観測")>=0)require_kind(ref(id,"前の観測"),"観測した段階");
        }else if(n.center=="局所変化") {
            at(ref(id,"対象"));if(text(id,"規則").empty())throw std::runtime_error("履歴の規則がありません");
            if(ref(id,"生成値")>=0&&!is_value(at(ref(id,"生成値")).center))throw std::runtime_error("履歴の生成値が値ではありません");
            if(ref(id,"入力値")>=0)for(Id value:items(ref(id,"入力値")))if(!is_value(at(value).center))throw std::runtime_error("履歴の入力が値ではありません");
        }
    }
    if(ref(root,"履歴")>=0) {
        std::set<Id> seen;
        for(Id h=ref(root,"履歴");h>=0;h=ref(h,"前の観測")) {
            require_kind(h,"観測した段階");if(!seen.insert(h).second)throw std::runtime_error("履歴が循環しています");
        }
    }
    // Values are finite immutable DAGs; program dependencies may be cyclic.
    // Iterative traversal also handles long lists without a host call stack.
    std::vector<unsigned char> color(nodes.size());
    for(size_t root_id=0;root_id<nodes.size();++root_id)if(is_value(nodes[root_id].center)&&!color[root_id]) {
        std::vector<std::pair<Id,bool>> pending{{static_cast<Id>(root_id),false}};
        while(!pending.empty()) {
            auto [id,exit]=pending.back();pending.pop_back();
            if(exit){color[id]=2;continue;}if(color[id]==2)continue;
            if(color[id]==1)throw std::runtime_error("格納値が循環しています");color[id]=1;
            pending.emplace_back(id,true);std::vector<Id> children;const auto& kind=at(id).center;
            if(kind=="列")children={ref(id,"先頭"),ref(id,"残り")};
            else if(kind=="記録")for(Id item:items(ref(id,"内容")))children.push_back(ref(item,"値"));
            else if(kind=="十字の値") {children.push_back(ref(id,"中央"));for(const auto& entry:structural_entries(*this,id))children.push_back(entry.second);}
            if(kind=="格子の値"||kind=="セル束"||kind=="格子の進行")children=grid_value_children(*this,id);
            for(Id child:children)pending.emplace_back(child,false);
        }
    }
}
void Space::save(const std::string& path) const {
    validate();
    const auto temporary=path+".writing";
    std::ofstream f(temporary, std::ios::binary | std::ios::trunc);
    if(!f) throw std::runtime_error("保存先を開けません");
    f<<"CROSS-IMAGE-1 "<<root<<' '<<nodes.size()<<'\n';
    for(const auto& n:nodes) {
        f<<std::quoted(n.center)<<'\n';
        for(const auto& a:n.arms) for(const auto* sites:{&a.faces,&a.edges,&a.vertices})
            for(const auto& p:*sites) f<<std::quoted(p.text)<<' '<<p.ref<<'\n';
    }
    f.flush(); if(!f) { std::remove(temporary.c_str()); throw std::runtime_error("書き込みに失敗しました"); }
    f.close();
    if(std::rename(temporary.c_str(),path.c_str())!=0) { std::remove(temporary.c_str()); throw std::runtime_error("保存の置換に失敗しました"); }
}
Space Space::load(const std::string& path, size_t budget) {
    Space s; s.limit=budget; const auto content=read_file(path);std::istringstream f(content); std::string format; size_t count=0;
    if(!(f>>format>>s.root>>count) || format!="CROSS-IMAGE-1" || count>budget || count>content.size()/300 || count>static_cast<size_t>(std::numeric_limits<Id>::max())) throw std::runtime_error("不正な保存形式または予算超過です");
    s.nodes.resize(count);
    for(auto& n:s.nodes) {
        if(!(f>>std::quoted(n.center))) throw std::runtime_error("保存が途中で切れています");
        for(auto& a:n.arms) for(auto* sites:{&a.faces,&a.edges,&a.vertices})
            for(auto& p:*sites) if(!(f>>std::quoted(p.text)>>p.ref)) throw std::runtime_error("面・辺・頂点の保存が壊れています");
    }
    f>>std::ws; if(!f.eof()) throw std::runtime_error("保存の末尾に余分なデータがあります");
    s.validate(); return s;
}
std::string read_file(const std::string& p,size_t maximum) {
    std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("開けません: "+p);
    std::string text;std::array<char,8192> buffer{};
    while(f){f.read(buffer.data(),buffer.size());size_t count=static_cast<size_t>(f.gcount());
        if(count>maximum-text.size())throw std::runtime_error("入力ファイルのバイト上限です: "+p);
        text.append(buffer.data(),count);}
    if(!f.eof())throw std::runtime_error("入力ファイルの読み取りに失敗しました: "+p);
    return text;
}
std::string quote_json(const std::string& text) {
    validate_utf8(text);
    std::ostringstream out; out<<'"';
    for(unsigned char c:text) {
        if(c=='"'||c=='\\') out<<'\\'<<c;
        else if(c<32) out<<"\\u"<<std::hex<<std::setw(4)<<std::setfill('0')<<int(c)<<std::dec;
        else out<<c;
    }
    out<<'"'; return out.str();
}

// The external-data converter accepts JSON, with a finite nesting budget.
class JsonReader {
    Space& s; const std::string& text; size_t p=0;
    void ws(){while(p<text.size() && (text[p]==' '||text[p]=='\t'||text[p]=='\r'||text[p]=='\n'))++p;}
    bool take(char c){ws();if(p<text.size()&&text[p]==c){++p;return true;}return false;}
    void expect(char c){if(!take(c))throw std::runtime_error("JSONの構文が不正です");}
    unsigned hex4(){unsigned n=0;for(int i=0;i<4;++i){if(p>=text.size())throw std::runtime_error("短いUnicodeエスケープ");char c=text[p++];n*=16;if(c>='0'&&c<='9')n+=c-'0';else if(c>='a'&&c<='f')n+=c-'a'+10;else if(c>='A'&&c<='F')n+=c-'A'+10;else throw std::runtime_error("Unicodeエスケープが不正です");}return n;}
    static void utf8(std::string& o,unsigned c){if(c<128)o+=char(c);else if(c<2048){o+=char(192|(c>>6));o+=char(128|(c&63));}else if(c<65536){o+=char(224|(c>>12));o+=char(128|((c>>6)&63));o+=char(128|(c&63));}else{o+=char(240|(c>>18));o+=char(128|((c>>12)&63));o+=char(128|((c>>6)&63));o+=char(128|(c&63));}}
    std::string string(){expect('"');std::string o;while(p<text.size()){unsigned char c=text[p++];if(c=='"')return o;if(c<32)throw std::runtime_error("JSON文字列に制御文字があります");if(c!='\\'){o+=char(c);continue;}if(p==text.size())break;char e=text[p++];if(e=='"'||e=='\\'||e=='/')o+=e;else if(e=='b')o+='\b';else if(e=='f')o+='\f';else if(e=='n')o+='\n';else if(e=='r')o+='\r';else if(e=='t')o+='\t';else if(e=='u'){unsigned u=hex4();if(u>=0xD800&&u<=0xDBFF){if(p+2>text.size()||text.substr(p,2)!="\\u")throw std::runtime_error("サロゲート対が不正です");p+=2;unsigned v=hex4();if(v<0xDC00||v>0xDFFF)throw std::runtime_error("サロゲート対が不正です");u=0x10000+(u-0xD800)*1024+v-0xDC00;}else if(u>=0xDC00&&u<=0xDFFF)throw std::runtime_error("不正なサロゲートです");utf8(o,u);}else throw std::runtime_error("未知のJSONエスケープです");}throw std::runtime_error("文字列が閉じていません");}
    Id value(int depth){if(depth>128)throw std::runtime_error("JSONの入れ子上限です");ws();if(p==text.size())throw std::runtime_error("値がありません");
        if(text[p]=='"')return s.string(string());
        if(take('[')){std::vector<Id> values;if(!take(']')){do{values.push_back(value(depth+1));}while(take(','));expect(']');}Id tail=s.add("空列");for(auto i=values.rbegin();i!=values.rend();++i){Id n=s.add("列");s.link(n,"先頭",*i);s.link(n,"残り",tail);tail=n;}return tail;}
        if(take('{')){std::vector<Id> entries;std::set<std::string> keys;if(!take('}')){do{std::string k=string();if(!keys.insert(k).second)throw std::runtime_error("JSONのキーが重複しています");expect(':');Id v=value(depth+1), key=s.string(k),entry=s.add("項目");s.link(entry,"名前",key);s.link(entry,"値",v);entries.push_back(entry);}while(take(','));expect('}');}Id bundle=s.sequence(entries),r=s.add("記録");s.link(r,"内容",bundle);return r;}
        for(const auto& literal:{std::string("true"),std::string("false"),std::string("null")})if(text.compare(p,literal.size(),literal)==0){p+=literal.size();return literal=="null"?s.add("無"):s.boolean(literal=="true");}
        size_t start=p;if(text[p]=='-')++p;if(p==text.size())throw std::runtime_error("数が途中です");if(text[p]=='0')++p;else{if(text[p]<'1'||text[p]>'9')throw std::runtime_error("数が不正です");while(p<text.size()&&text[p]>='0'&&text[p]<='9')++p;}
        bool decimal=false;for(char marker:{'.','e'}){if(p<text.size()&&(text[p]==marker||(marker=='e'&&text[p]=='E'))){decimal=true;++p;if(marker=='e'&&p<text.size()&&(text[p]=='+'||text[p]=='-'))++p;size_t digits=p;while(p<text.size()&&text[p]>='0'&&text[p]<='9')++p;if(digits==p)throw std::runtime_error("数の桁がありません");}}
        auto lex=text.substr(start,p-start);if(!decimal){size_t consumed;auto n=std::stoll(lex,&consumed);if(consumed!=lex.size())throw std::runtime_error("整数が不正です");return s.integer(n);}Id i=s.add("小数");s.text(i,"値",lex);return i;
    }
public:JsonReader(Space& sp,const std::string& t):s(sp),text(t){} Id parse(){Id i=value(0);ws();if(p!=text.size())throw std::runtime_error("JSONの末尾が不正です");return i;}
};
Id import_json(Space& s,const std::string& text){validate_utf8(text);return JsonReader(s,text).parse();}
std::string export_json(const Space& s,Id value){
    std::set<Id> active;
    std::function<std::string(Id,int)> visit=[&](Id i,int depth)->std::string{
        if(depth>256||!active.insert(i).second)throw std::runtime_error("値の循環または深さ上限です");
        const auto n=s.at(i);std::string out;
        if(n.center=="整数"||n.center=="小数")out=s.text(i,"値");
        else if(n.center=="文章")out=quote_json(s.text(i,"値"));
        else if(n.center=="真偽")out=s.text(i,"値")=="真"?"true":"false";
        else if(n.center=="無")out="null";
        else if(n.center=="失敗")out="{\"失敗\":"+quote_json(s.text(i,"理由"))+"}";
        else if(n.center=="計画の値")out="{\"計画\":"+quote_json(s.text(s.ref(i,"定義"),"名前"))+"}";
        else if(n.center=="列"||n.center=="空列"){out="[";Id current=i;std::set<Id> seen;while(s.at(current).center=="列"){if(!seen.insert(current).second)throw std::runtime_error("列が循環しています");if(out!="[")out+=",";out+=visit(s.ref(current,"先頭"),depth+1);current=s.ref(current,"残り");}if(s.at(current).center!="空列")throw std::runtime_error("列の末尾が不正です");out+="]";}
        else if(n.center=="記録"){out="{";for(Id e:s.items(s.ref(i,"内容"))){if(out!="{")out+=",";out+=quote_json(s.text(s.ref(e,"名前"),"値"))+":"+visit(s.ref(e,"値"),depth+1);}out+="}";}
        else if(n.center=="格子の値"){
            out="{\"格子\":{\"形状\":"+visit(s.ref(i,"形状"),depth+1)+",\"境界\":"+quote_json(s.text(i,"境界"))+",\"外側\":"+visit(s.ref(i,"外側"),depth+1)+",\"セル\":[";
            bool first=true;for(Id cell:grid_cells(s,i)){if(!first)out+=",";first=false;out+=visit(cell,depth+1);}out+="]}}";
        }
        else if(n.center=="セル束"||n.center=="格子の進行"){throw std::runtime_error("内部セル束は格子の確定前には出力できません");}
        else if(n.center=="十字の値"){
            out="{\"十字\":{\"中央\":"+visit(s.ref(i,"中央"),depth+1)+",\"場所\":{";bool first=true;
            for(const auto& [name,value]:structural_entries(s,i)){if(!first)out+=",";first=false;out+=quote_json(name)+":"+visit(value,depth+1);}out+="}}}";
        }
        else throw std::runtime_error("JSONへ変換できる値ではありません");active.erase(i);return out;
    };return visit(value,0);
}
}
