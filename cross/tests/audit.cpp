#include "cross.hpp"
#include <algorithm>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <random>

using namespace cross;
void check(bool condition,const std::string& message){if(!condition)throw std::runtime_error(message);}
void reject(const std::function<void()>& fn){bool caught=false;try{fn();}catch(const std::exception&){caught=true;}check(caught,"invalid state accepted");}
std::string example(const std::string& name){return read_file(std::string(EXAMPLE_DIR)+"/"+name+".cross");}
Id op(Space& s,const std::string& name,const std::vector<Id>& args){
    Id id=s.add(name);auto names=roles(name);check(names.size()==args.size(),"arity");
    for(size_t i=0;i<args.size();++i)s.link(id,names[i],args[i]);return id;
}
void identical(const Space& a,const Space& b){
    check(a.root==b.root&&a.nodes.size()==b.nodes.size(),"state size mismatch");
    for(size_t i=0;i<a.nodes.size();++i){
        check(a.nodes[i].center==b.nodes[i].center,"center mismatch");
        for(int arm=0;arm<6;++arm){
            const auto& x=a.nodes[i].arms[arm];const auto& y=b.nodes[i].arms[arm];
            for(const auto& pair:{std::make_pair(&x.faces,&y.faces),std::make_pair(&x.edges,&y.edges),std::make_pair(&x.vertices,&y.vertices)})
                for(int k=0;k<4;++k)check((*pair.first)[k].text==(*pair.second)[k].text&&(*pair.first)[k].ref==(*pair.second)[k].ref,"slot mismatch");
        }
    }
}
void compare(const Space& source,const std::string& policy,uint64_t seed=1,size_t steps=10000){
    auto a=source,b=source;
    auto ra=Machine(a).run(policy,steps,seed,"events"),rb=Machine(b).run(policy,steps,seed,"scan");
    check(ra.status==rb.status&&ra.value==rb.value&&ra.steps==rb.steps&&ra.transitions==rb.transitions&&ra.max_enabled==rb.max_enabled,"scheduler report mismatch");
    identical(a,b);a.validate();b.validate();
}
void unchecked_save(const Space& s,const std::string& path){
    std::ofstream f(path);f<<"CROSS-IMAGE-1 "<<s.root<<' '<<s.nodes.size()<<'\n';
    for(const auto& n:s.nodes){f<<std::quoted(n.center)<<'\n';for(const auto& a:n.arms)
        for(const auto* sites:{&a.faces,&a.edges,&a.vertices})for(const auto& p:*sites)f<<std::quoted(p.text)<<' '<<p.ref<<'\n';}
}
Space graph(size_t count,bool chain,size_t dormant=0){
    Space s;s.root=s.add("計算空間");Id one=s.integer(1);std::vector<Id> level;
    for(size_t i=0;i<count;++i)level.push_back(op(s,"足す",{one,one}));
    if(chain){Id v=level[0];for(size_t i=1;i<level.size();++i)v=op(s,"足す",{v,level[i]});level={v};}
    else while(level.size()>1){std::vector<Id> next;for(size_t i=0;i<level.size();i+=2)next.push_back(i+1<level.size()?op(s,"足す",{level[i],level[i+1]}):level[i]);level=next;}
    s.link(s.root,"実行",level[0]);
    for(size_t i=0;i<dormant;++i)s.string("無関係な保存資料");
    return s;
}
Space permute_ids(const Space& source,uint64_t seed){
    std::vector<Id> ids(source.nodes.size());std::iota(ids.begin(),ids.end(),0);std::mt19937_64 rng(seed);std::shuffle(ids.begin(),ids.end(),rng);
    Space out=source;out.root=ids[source.root];
    for(size_t i=0;i<ids.size();++i){out.at(ids[i])=source.nodes[i];for(auto& a:out.at(ids[i]).arms)
        for(auto* sites:{&a.faces,&a.edges,&a.vertices})for(auto& p:*sites)if(p.ref>=0)p.ref=ids[p.ref];}
    return out;
}
int tests(){
    int passed=0,failed=0;
    auto test=[&](const std::string& name,const std::function<void()>& fn){try{fn();++passed;std::cout<<"PASS "<<name<<'\n';}catch(const std::exception& e){++failed;std::cout<<"FAIL "<<name<<": "<<e.what()<<'\n';}};
    const std::string checkpoint="audit-checkpoint.cross-image";
    test("all examples: events/scan produce identical full images for four policies",[]{
        for(const auto& name:{"parallel","factorial","branch","faces-edges-vertices","sum","concat","meaning"}){
            auto code=example(name);std::string input="null";
            if(std::string(name)=="sum")input="[3,5,8,13,21]";
            if(std::string(name)=="concat")input="[[\"春\",\"夏\"],[\"秋\",\"冬\"]]";
            if(std::string(name)=="meaning")code=read_file(std::string(EXAMPLE_DIR)+"/../stdlib/meaning.cross")+"\n"+code;
            auto s=compile(code,input);
            const std::map<std::string,std::string> answers{{"parallel","24"},{"factorial","720"},{"branch",quote_json("選んだ枝だけが動く")},{"faces-edges-vertices","360"},{"sum","50"},{"concat","[\"春\",\"夏\",\"秋\",\"冬\"]"},{"meaning","400"}};
            auto checked=s;auto done=Machine(checked).run();
            check(done.status=="COMPLETE"&&export_json(checked,done.value)==answers.at(name),"example oracle mismatch: "+std::string(name));
            for(const auto& policy:{"batch","forward","reverse","random"})compare(s,policy,39);
        }
    });
    test("40 generated DAGs, shared inputs, branches: independent integer oracle and shuffled IDs",[]{
        for(uint64_t seed=1;seed<=40;++seed){
            std::mt19937_64 rng(seed);Space s;s.root=s.add("計算空間");
            std::vector<Id> ids;std::vector<int64_t> expected;
            for(int i=0;i<8;++i){expected.push_back(static_cast<int64_t>(rng()%21)-10);ids.push_back(s.integer(expected.back()));}
            for(int i=0;i<50;++i){
                size_t a=rng()%ids.size(),b=rng()%ids.size();auto type=rng()%3;
                if(type==2){bool c=rng()%2;Id condition=s.boolean(c);ids.push_back(op(s,"選ぶ",{condition,ids[a],ids[b]}));expected.push_back(c?expected[a]:expected[b]);}
                else{ids.push_back(op(s,type?"引く":"足す",{ids[a],ids[b]}));expected.push_back(type?expected[a]-expected[b]:expected[a]+expected[b]);}
            }
            s.link(s.root,"実行",ids.back());
            for(const auto& policy:{"batch","forward","reverse","random"}){
                compare(s,policy,seed);
                auto reordered=permute_ids(s,seed);auto r=Machine(reordered).run(policy,10000,seed);
                check(r.status=="COMPLETE"&&export_json(reordered,r.value)==std::to_string(expected.back()),"oracle / id ordering mismatch");
            }
        }
    });
    test("all 720 arm permutations preserve roles and answer: geometry is not intrinsic",[]{
        auto original=compile(example("faces-edges-vertices"));std::array<int,6> p{0,1,2,3,4,5};size_t count=0;
        do{auto s=original;for(auto& n:s.nodes){const auto old=n.arms;for(int i=0;i<6;++i)n.arms[p[i]]=old[i];}
            auto r=Machine(s).run();check(r.status=="COMPLETE"&&export_json(s,r.value)=="360","arm permutation mismatch");++count;
        }while(std::next_permutation(p.begin(),p.end()));check(count==720,"permutation count");
    });
    test("every early recursive checkpoint rebuilds event dependencies after reload",[&]{
        auto original=compile(example("factorial"));
        for(size_t step=0;step<=45;++step){
            auto s=original;auto partial=Machine(s).run("batch",step);check(partial.status=="STEP_BUDGET","not an early checkpoint");
            s.save(checkpoint);auto restored=Space::load(checkpoint);compare(restored,"random",step+1);
            auto done=Machine(restored).run("reverse");check(done.status=="COMPLETE"&&export_json(restored,done.value)=="720","resume mismatch");
        }
    });
    test("allocation failure at every allocation of expansion rolls back and can retry",[]{
        auto base=compile(example("factorial"));
        for(size_t step=0;step<100;++step){
            Machine m(base);m.request(m.output());auto ts=m.enabled();
            bool expansion=std::any_of(ts.begin(),ts.end(),[](const auto& t){return t.rule=="計画を展開";});
            if(!expansion){m.run("batch",1);continue;}
            auto complete=base;Machine(complete).run("batch",1);size_t required=complete.nodes.size()-base.nodes.size();check(required>0,"no expansion allocation");
            for(size_t extra=0;extra<required;++extra)for(const auto& scheduler:{"events","scan"}){
                auto s=base;s.limit=s.nodes.size()+extra;auto r=Machine(s).run("batch",1,1,scheduler);
                check(r.status=="NODE_BUDGET","budget did not interrupt");identical(s,base);s.validate();
                s.limit=100000;auto done=Machine(s).run();check(done.status=="COMPLETE"&&export_json(s,done.value)=="720","retry failed");
            }return;
        }throw std::runtime_error("expansion not reached");
    });
    test("blocked gate, cycles, type failure and unknown scheduler",[]{
        auto gate=example("faces-edges-vertices");auto p=gate.find("「許可」は真");check(p!=std::string::npos,"gate missing");gate.replace(p,std::string("「許可」は真").size(),"「許可」は偽");
        for(const auto& source:{gate,std::string("「甲」は「乙」。\n「乙」は「甲」。\n出力は「甲」。"),std::string("「答え」は文「x」と数「1」を足す。\n出力は「答え」。")}){
            auto s=compile(source);for(const auto& policy:{"batch","forward","reverse","random"})compare(s,policy,5);
        }
        auto s=compile("出力は数「1」。");reject([&]{Machine(s).run("batch",10,1,"unknown");});
    });
    test("infinite unused branch stays unrequested; explicit eager branch wakes",[]{
        auto s=compile("「循環」は「循環」。\n「答え」は真なら数「7」、そうでなければ「循環」を選ぶ。\n出力は「答え」。");
        for(const auto& scheduler:{"events","scan"}){
            auto lazy=s;auto r=Machine(lazy).run("batch",100,1,scheduler);check(r.status=="COMPLETE"&&export_json(lazy,r.value)=="7","lazy branch");
            auto eager=s;Id branch=-1;for(size_t i=0;i<eager.nodes.size();++i)if(eager.nodes[i].center=="選ぶ"){eager.nodes[i].port("偽の枝").edges[3].text="先に要求";branch=eager.ref(static_cast<Id>(i),"偽の枝");}
            r=Machine(eager).run("batch",100,1,scheduler);check(r.status=="COMPLETE"&&eager.text(branch,"要求")=="有効","eager branch request lost");
        }
    });
    test("malformed persisted scalars rejected, including old COMPLETE invalid JSON repro",[&]{
        for(const auto& pair:{std::make_pair("整数","1,2"),std::make_pair("整数","9223372036854775808"),std::make_pair("小数","0.0,2"),std::make_pair("真偽","maybe")}){
            auto s=compile("出力は数「1」。");Id out=s.ref(s.root,"実行");s.at(out).center=pair.first;s.text(out,"値",pair.second);
            unchecked_save(s,checkpoint);reject([&]{Space::load(checkpoint);});reject([&]{Machine invalid(s);});
        }
    });
    test("invalid result, missing inputs, invalid passed vertex and conflicting aliases rejected",[&]{
        for(int variant=0;variant<4;++variant){
            auto s=compile("言葉「加算」は動き「足す」を表す。\n「答え」は数「1」と数「2」を加算。\n出力は「答え」。");Id out=s.ref(s.root,"実行");
            if(variant==0)s.at(out).port("結果").vertices[0].ref=s.root;
            if(variant==1)s.at(out).port("対象").edges[0].ref=-1;
            if(variant==2){auto& a=s.at(out).port("対象");a.vertices[2].text="通過";}
            if(variant==3){Id registry=s.ref(s.root,"規則集"),alias=s.items(registry)[0];s.text(alias,"動き","未実装");}
            unchecked_save(s,checkpoint);reject([&]{Space::load(checkpoint);});
        }
    });
    test("10000 dormant nodes do not multiply execution inspections",[]{
        auto small=graph(32,false),large=graph(32,false,10000);
        auto a=Machine(small).run(),b=Machine(large).run();
        check(a.status=="COMPLETE"&&b.status=="COMPLETE"&&a.node_inspections==b.node_inspections,"dormant space scanned per step");
        check(b.index_nodes==a.index_nodes+10000,"initial index cost not accounted");
    });
    std::filesystem::remove(checkpoint);
    std::cout<<"AUDIT RESULT "<<passed<<" passed, "<<failed<<" failed\n";return failed?1:0;
}
void measurements(const std::string& path){
    std::ofstream file(path);file<<"{\"scope\":\"same Node layout, semantics, validation and history; compile and Space copy excluded from time; 3-run median\",\"node_size_bytes\":"<<sizeof(Node)<<",\"cases\":[";bool first=true;
    for(const auto& config:{std::make_tuple(64,false,0),std::make_tuple(256,false,0),std::make_tuple(256,true,0),std::make_tuple(64,false,10000)}){
        auto [width,chain,dormant]=config;auto base=graph(width,chain,dormant);compare(base,"batch");
        if(!first)file<<',';first=false;file<<"{\"shape\":"<<quote_json(chain?"chain":"balanced")<<",\"width\":"<<width<<",\"dormant\":"<<dormant<<",\"initial_nodes\":"<<base.nodes.size();
        for(const auto& scheduler:{"events","scan"}){
            std::vector<double> times;Report report;size_t final_nodes=0;
            for(int repeat=0;repeat<3;++repeat){auto s=base;auto start=std::chrono::steady_clock::now();report=Machine(s).run("batch",10000,1,scheduler);times.push_back(std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count());
                check(report.status=="COMPLETE"&&export_json(s,report.value)==std::to_string(width*2),"benchmark oracle");final_nodes=s.nodes.size();}
            std::sort(times.begin(),times.end());file<<",\""<<scheduler<<"\":{\"median_ms\":"<<times[1]<<",\"node_inspections\":"<<report.node_inspections<<",\"index_nodes\":"<<report.index_nodes<<",\"steps\":"<<report.steps<<",\"transitions\":"<<report.transitions<<",\"max_enabled\":"<<report.max_enabled<<",\"final_nodes\":"<<final_nodes<<'}';
        }file<<'}';
    }file<<"]}\n";check(bool(file),"benchmark output failed");
}
int main(int argc,char** argv){try{if(argc==3&&std::string(argv[1])=="--measure"){measurements(argv[2]);return 0;}return tests();}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
