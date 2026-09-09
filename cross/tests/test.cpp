#include "cross.hpp"
#include <algorithm>
#include <filesystem>
#include <functional>
#include <iostream>
#include <numeric>

using namespace cross;
int passed=0,failed=0;
void require(bool okay,const std::string& message){if(!okay)throw std::runtime_error(message);}
void test(const std::string& name,const std::function<void()>& fn){try{fn();++passed;std::cout<<"PASS "<<name<<'\n';}catch(const std::exception& e){++failed;std::cout<<"FAIL "<<name<<": "<<e.what()<<'\n';}}
void rejects(const std::function<void()>& fn){bool threw=false;try{fn();}catch(const std::exception&){threw=true;}require(threw,"拒否されなかった");}
std::string example(const std::string& name){return read_file(std::string(EXAMPLE_DIR)+"/"+name+".cross");}
void replace_once(std::string& text,const std::string& from,const std::string& to){auto p=text.find(from);require(p!=std::string::npos,"置換元がない");text.replace(p,from.size(),to);}
std::string evaluate(const std::string& program,const std::string& policy="batch",const std::string& input="null"){
    auto s=compile(program,input);auto r=Machine(s).run(policy);require(r.status=="COMPLETE",report_json(s,r));s.validate();return export_json(s,r.value);
}
int main(){
    test("自然文・前方参照・定義した語義",[]{require(evaluate(example("parallel"))=="24","計算結果");});
    test("四つの選択順で再帰の結果が一致",[]{for(const auto& policy:{"batch","forward","reverse","random"})require(evaluate(example("factorial"),policy)=="720",policy);});
    test("文順を命令順にしない",[]{auto text=example("parallel");auto pos=text.find("「答え」は");auto end=text.find("。",pos)+3;auto sentence=text.substr(pos,end-pos);text.erase(pos,end-pos);text.insert(text.find("出力は"),sentence+"\n");require(evaluate(text)=="24","順序依存");});
    test("選ばれなかった枝の除算は動かない",[]{auto s=compile(example("branch"));auto r=Machine(s).run();require(r.status=="COMPLETE","未選択枝で失敗");for(const auto& n:s.nodes)if(n.center=="割る")require(n.port("要求").faces[1].text.empty(),"不要な要求");});
    test("資料を構造に変換して再帰計算",[]{for(const auto& [data,expected]:std::vector<std::pair<std::string,std::string>>{{"[]","0"},{"[7]","7"},{"[3,5,8,13,21]","50"}})require(evaluate(example("sum"),"batch",data)==expected,"合計");});
    test("面・辺・頂点を混在して実行",[]{require(evaluate(example("faces-edges-vertices"))=="360","小計");});
    test("入力辺の付け替えが計算を変える",[]{auto text=example("faces-edges-vertices");replace_once(text,"は「単価」から受け取る","は数「5」から受け取る");require(evaluate(text)=="15","辺が装飾になっている");});
    test("初期頂点の値が計算を変える",[]{auto text=example("faces-edges-vertices");replace_once(text,"頂点「北東端」は数「3」","頂点「北東端」は数「4」");require(evaluate(text)=="480","頂点が装飾になっている");});
    test("閉じた許可辺を通らない",[]{auto text=example("faces-edges-vertices");replace_once(text,"「許可」は真","「許可」は偽");auto s=compile(text);auto r=Machine(s).run();require(r.status=="BLOCKED"&&r.value<0,"許可を無視した");});
    test("面の細かい制約を辺が検査する",[]{auto text=example("faces-edges-vertices");replace_once(text,"数「120」","数「-1」");auto s=compile(text);auto r=Machine(s).run();require(r.status=="ERROR","正の制約を無視した");});
    test("型の面を変更すると型エラー",[]{auto text=example("faces-edges-vertices");replace_once(text,"面「東」は「整数」","面「東」は「文章」");auto s=compile(text);require(Machine(s).run().status=="ERROR","型を無視した");});
    test("曖昧な文・未定義名・外部コードを拒否",[]{for(const auto& text:{"いい感じに計算して。","出力は「ない」。","「値」はsystem(\"echo bad\")。\n出力は「値」。"})rejects([&]{compile(text);});});
    test("入力辺と初期頂点の重複を拒否",[]{auto text=example("faces-edges-vertices");replace_once(text,"出力は", "十字「小計」の腕「-x」の辺「北東」は数「8」から受け取る。\n出力は");rejects([&]{compile(text);});});
    test("保存から実行状態を再開",[]{auto s=compile(example("factorial"));auto r=Machine(s).run("batch",30);require(r.status=="STEP_BUDGET","途中停止でない");auto path=std::filesystem::temp_directory_path()/"cross-native-test-checkpoint.cross-image";s.save(path.string());auto restored=Space::load(path.string());std::filesystem::remove(path);auto done=Machine(restored).run("reverse");require(done.status=="COMPLETE"&&export_json(restored,done.value)=="720","再開できない");});
    test("計画を値として渡す",[]{auto source=std::string("計画「倍」は「数」を受け取る。\n「答え」は「数」と数「2」を掛ける。\n返すのは「答え」。\n計画を終える。\n「方法」は計画「倍」。\n「答え」は「方法」に数「9」を渡す。\n出力は「答え」。");require(evaluate(source)=="18","計画が値でない");});
    test("循環した依存を保留",[]{auto s=compile("「甲」は「乙」。\n「乙」は「甲」。\n出力は「甲」。");require(Machine(s).run().status=="STUCK","循環で捏造した");});
    test("ノード不足の局所段階を巻き戻す",[]{auto s=compile(example("parallel"));Machine m(s);m.request(m.output());auto before=s.nodes.size();auto root=s.ref(s.root,"履歴");s.limit=before+1;auto r=m.run();require(r.status=="NODE_BUDGET"&&s.nodes.size()==before&&s.ref(s.root,"履歴")==root,"部分更新が残った");s.validate();s.limit=100000;require(m.run().status=="COMPLETE","再開失敗");});
    test("整数の範囲と除算エラー",[]{for(const auto& expr:{"数「9223372036854775807」と数「1」を足す","数「7」を数「0」で割る","数「1」を数「2」で割る"}){auto s=compile(std::string("「答え」は")+expr+"。\n出力は「答え」。");require(Machine(s).run().status=="ERROR","不正算術");}});
    test("JSONの全型とUnicodeを往復",[]{Space s;s.root=s.add("資料空間");auto i=import_json(s,"{\"文\":\"a\\n\\u65e5\\ud83d\\ude00\",\"値\":[true,false,null,-12,1.25,2e3]}");s.link(s.root,"資料",i);auto text=export_json(s,i);Space second;second.root=second.add("資料空間");Id j=import_json(second,text);second.link(second.root,"資料",j);require(export_json(second,j)==text,"情報が欠落した");s.validate();});
    test("不正JSON・循環した値を拒否",[]{for(const auto& data:{"[1,]","{\"x\":1,\"x\":2}","01","\"\\ud800\""})rejects([&]{Space s;import_json(s,data);});Space s;Id empty=s.add("空列"),head=s.integer(1),list=s.add("列");s.link(list,"先頭",head);s.link(list,"残り",list);(void)empty;rejects([&]{export_json(s,list);});});
    test("六腕の回転は関係を保持する",[]{std::array<int,3> perm{0,1,2};int count=0;const std::array<std::array<int,3>,6> axes{{{1,0,0},{-1,0,0},{0,1,0},{0,-1,0},{0,0,1},{0,0,-1}}};
        do{int inversions=0;for(int i=0;i<3;++i)for(int j=i+1;j<3;++j)inversions+=perm[i]>perm[j];for(int bits=0;bits<8;++bits){std::array<int,3> signs;int determinant=(inversions%2?-1:1);for(int j=0;j<3;++j){signs[j]=(bits&(1<<j))?-1:1;determinant*=signs[j];}if(determinant!=1)continue;auto s=compile(example("faces-edges-vertices"));for(auto& n:s.nodes){auto old=n.arms;for(int src=0;src<6;++src){std::array<int,3> v;for(int j=0;j<3;++j)v[j]=signs[j]*axes[src][perm[j]];auto dst=std::find(axes.begin(),axes.end(),v)-axes.begin();n.arms[dst]=old[src];}}auto r=Machine(s).run();require(r.status=="COMPLETE"&&export_json(s,r.value)=="360","回転が値を変えた");++count;}}while(std::next_permutation(perm.begin(),perm.end()));require(count==24,"24回転でない");});
    test("独立した中心が同じ段階で有効になる",[]{auto s=compile(example("parallel"));auto r=Machine(s).run();require(r.max_enabled>=2,"逐次命令列になっている");});
    test("基本の意味パターンと用途別パターンを合成",[]{auto library=read_file((std::filesystem::path(EXAMPLE_DIR).parent_path()/"stdlib/meaning.cross").string());auto s=compile(library+"\n"+example("meaning"));auto r=Machine(s).run();require(r.status=="COMPLETE"&&export_json(s,r.value)=="400","金額の意味束縛");size_t count=0;for(const auto& n:s.nodes)count+=n.center=="意味パターン";require(count==15,"意味が構造内に保存されていない");});
    test("意味は表面の語順でなく束縛した役割に従う",[]{auto source=std::string("意味「{差}を{元}から取り除いた数」=中心「引く」（左={元}:整数、右={差}:整数）。\n「答え」は数「3」を数「10」から取り除いた数。\n出力は「答え」。");require(evaluate(source)=="7","語順を役割と取り違えた");});
    test("意味パターンの即値と値の制約",[]{auto library=read_file((std::filesystem::path(EXAMPLE_DIR).parent_path()/"stdlib/meaning.cross").string());require(evaluate(library+"\n「答え」は数「9」の二倍。\n出力は「答え」。")=="18","固定部品を束縛できない");auto text=example("meaning");replace_once(text,"数「120」","数「-120」");auto s=compile(library+"\n"+text);require(Machine(s).run().status=="ERROR","意味の非負制約を無視した");});
    test("意味パターンから利用者の再帰計画を呼べる",[]{auto source=example("factorial");replace_once(source,"「計算」は計画「階乗」に数「6」を渡す。","意味「{値}の階乗」＝計画「階乗」（入力＝{値}:整数）。\n「計算」は数「6」の階乗。");require(evaluate(source)=="720","計画への意味対応が動かない");});
    test("複数の意味を勝手に優先順位で選ばない",[]{std::string source="意味「{a}と{b}をまとめた値」＝中心「足す」（左＝{a}:整数、右＝{b}:整数）。\n意味「{a}と{b}をまとめた値」＝中心「掛ける」（左＝{a}:整数、右＝{b}:整数）。\n「答え」は数「2」と数「3」をまとめた値。\n出力は「答え」。";rejects([&]{compile(source);});});
    test("標準構文と衝突する意味も曖昧として扱う",[]{std::string source="意味「{a}と{b}を足す」＝中心「掛ける」（左＝{a}:整数、右＝{b}:整数）。\n「答え」は数「2」と数「3」を足す。\n出力は「答え」。";rejects([&]{compile(source);});});
    test("未束縛・未使用・不足の意味パターンを拒否",[]{for(const auto& declaration:{"意味「{a}の変換」＝中心「足す」（左＝{a}:整数）。","意味「{a}の変換」＝中心「参照」（対象＝{b}:整数）。","意味「{a}の変換」＝中心「参照」（対象＝数「1」:整数）。"})rejects([&]{compile(std::string(declaration)+"\n出力は数「0」。");});});
    test("意味パターンの文章即値に読点を含められる",[]{auto source=std::string("意味「{名}への挨拶」＝中心「つなぐ」（左＝文「こんにちは、」:文章、右＝{名}:文章）。\n「答え」は文「世界」への挨拶。\n出力は「答え」。");require(evaluate(source)==quote_json("こんにちは、世界"),"読点が束縛の区切りに化けた");});
    test("先行要求の辺が実際に要求を伝える",[]{auto source=std::string("「未使用」は数「10」を数「0」で割る。\n十字「選択」の中心は「選ぶ」。\n十字「選択」の腕「+x」の面「北」は「条件」。\n十字「選択」の腕「+x」の頂点「北東端」は真。\n十字「選択」の腕「-x」の面「北」は「真の枝」。\n十字「選択」の腕「-x」の頂点「北東端」は数「7」。\n十字「選択」の腕「+y」の面「北」は「偽の枝」。\n十字「選択」の腕「+y」の辺「北東」は「未使用」から受け取る。\n十字「選択」の腕「+y」の辺「北西」は先に要求。\n出力は「選択」。");auto eager=compile(source);auto r=Machine(eager).run();require(r.status=="COMPLETE"&&export_json(eager,r.value)=="7","未使用の枝が出力を変えた");bool requested=false;for(const auto& n:eager.nodes)if(n.center=="割る"&&!n.port("要求").faces[1].text.empty())requested=true;require(requested,"辺が要求を伝えなかった");replace_once(source,"先に要求","必要時だけ");auto lazy=compile(source);Machine(lazy).run();for(const auto& n:lazy.nodes)if(n.center=="割る")require(n.port("要求").faces[1].text.empty(),"通常辺も先行要求した");});
    std::cout<<"RESULT "<<passed<<" passed, "<<failed<<" failed\n";return failed?1:0;
}
