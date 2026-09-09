#include "cross.hpp"
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <set>

using namespace cross;
void check(bool ok,const std::string& why){if(!ok)throw std::runtime_error(why);}
void rejects(const std::function<void()>& f){bool caught=false;try{f();}catch(const std::exception&){caught=true;}check(caught,"expected rejection");}
std::string fixture(const std::string& file){return read_file(std::string(EXAMPLE_DIR)+"/"+file);}
Id move(Space& s,Id value,const std::string& axis,int turns){return structural_compute(s,"十字を回す",{value,s.string(axis),s.integer(turns)});}
Id put(Space& s,Id value,const std::string& address,Id next){return structural_compute(s,"場所に置く",{value,s.string(address),next});}
Id get(Space& s,Id value,const std::string& address){return structural_compute(s,"場所を読む",{value,s.string(address)});}
std::string cells_json(const std::vector<bool>& cells){std::string out="[";for(bool c:cells){if(out!="[")out+=",";out+=c?"true":"false";}return out+"]";}
std::vector<bool> reference(std::vector<bool> cells,int steps){
    for(int generation=0;generation<steps&&!cells.empty();++generation){auto next=cells;
        for(size_t i=0;i<cells.size();++i)next[i]=cells[(i+cells.size()-1)%cells.size()]!=cells[(i+1)%cells.size()];cells=std::move(next);}
    return cells;
}
int main(){
    int passed=0,failed=0;
    auto test=[&](const char* name,const std::function<void()>& f){try{f();++passed;std::cout<<"PASS "<<name<<'\n';}catch(const std::exception& e){++failed;std::cout<<"FAIL "<<name<<": "<<e.what()<<'\n';}};
    const std::string library=fixture("../stdlib/structure.cross")+"\n";
    test("all 72 locations hold values; writes preserve previous versions",[]{
        Space s;s.root=s.add("資料空間");Id cross=structural_compute(s,"十字を作る",{s.string("中心")});s.link(s.root,"資料",cross);
        int count=0;
        for(const auto& arm:{"+x","-x","+y","-y","+z","-z"})for(int kind=0;kind<3;++kind)for(const auto& site:kind==0?std::vector<std::string>{"北","南","東","西"}:kind==1?std::vector<std::string>{"北東","南東","南西","北西"}:std::vector<std::string>{"北東端","南東端","南西端","北西端"}){
            std::string location=std::string(arm)+"/"+(kind==0?"面":kind==1?"辺":"頂点")+"/"+site;
            Id before=cross,value=s.integer(++count);cross=put(s,cross,location,value);
            check(get(s,cross,location)==value,"lost slot value");rejects([&]{get(s,before,location);});
        }
        s.link(s.root,"資料",cross);s.validate();check(structural_entries(s,cross).size()==72,"missing locations");
        const auto original=export_json(s,cross);
        for(const auto& axis:{"+x","-x","+y","-y","+z","-z"}){
            check(export_json(s,move(s,cross,axis,4))==original,"four turns not identity");
            check(export_json(s,move(s,move(s,cross,axis,1),axis,-1))==original,"inverse did not cancel");
        }
        s.save("structure-test.cross-image");auto restored=Space::load("structure-test.cross-image");
        check(export_json(restored,restored.ref(restored.root,"資料"))==original,"72-slot persistence failed");
    });
    test("proper cube rotations have 24 orientations, including face/edge/vertex frame changes",[]{
        Space s;s.root=s.add("資料空間");Id value=structural_compute(s,"十字を作る",{s.integer(0)});s.link(s.root,"資料",value);
        value=put(s,value,"+x/面/北",s.integer(7));value=put(s,value,"+y/面/北",s.integer(11));
        value=put(s,value,"+z/面/北",s.integer(13));value=put(s,value,"+z/辺/北東",s.integer(17));value=put(s,value,"+z/頂点/北東端",s.integer(19));
        Id rotated=move(s,value,"+z",1);
        check(s.text(get(s,rotated,"+y/面/北"),"値")=="7","world axis rotation");
        check(s.text(get(s,rotated,"+z/面/西"),"値")=="13","face normal rotation");
        check(s.text(get(s,rotated,"+z/辺/北西"),"値")=="17","edge rotation");
        check(s.text(get(s,rotated,"+z/頂点/北西端"),"値")=="19","vertex rotation");
        check(export_json(s,move(s,move(s,value,"+x",1),"+y",1))!=export_json(s,move(s,move(s,value,"+y",1),"+x",1)),"rotations incorrectly commute");
        std::set<std::string> seen;std::vector<Id> pending{value};
        while(!pending.empty()){Id next=pending.back();pending.pop_back();if(!seen.insert(export_json(s,next)).second)continue;
            check(seen.size()<=24,"reflection or invalid orientation generated");for(const auto& axis:{"+x","+y","+z"})pending.push_back(move(s,next,axis,1));}
        check(seen.size()==24,"not the cube rotation group");
    });
    test("records retain missing/null distinction and immutable updates",[]{
        Space s;s.root=s.add("資料空間");Id record=import_json(s,"{\"有る\":null,\"a\":[1,2]}");s.link(s.root,"資料",record);
        Id name=s.string("有る"),missing=s.string("無い");
        check(s.at(structural_compute(s,"項目を読む",{record,name})).center=="無","null lost");
        rejects([&]{structural_compute(s,"項目を読む",{record,missing});});
        Id changed=structural_compute(s,"項目に置く",{record,missing,s.integer(8)});
        check(export_json(s,record)=="{\"有る\":null,\"a\":[1,2]}","record mutated");
        check(s.text(structural_compute(s,"項目を読む",{changed,missing}),"値")=="8","new key lost");
    });
    test("cross operations compile through meaning patterns and resume under all policies",[&]{
        auto code=library+fixture("rotation.cross");
        for(const auto& policy:{"batch","forward","reverse","random"})for(const auto& scheduler:{"events","scan"}){
            auto s=compile(code);Machine(s).run(policy,12,27,scheduler);s.save("structure-test.cross-image");
            auto reloaded=Space::load("structure-test.cross-image");auto r=Machine(reloaded).run(policy,10000,27,scheduler);
            check(r.status=="COMPLETE"&&export_json(reloaded,r.value)=="7","rotation resume failed");
        }
    });
    test("user-written cellular automaton: 30 variable-input cases vs independent simultaneous oracle",[&]{
        auto code=library+fixture("rule90.cross");int cases=0;
        for(int width:{0,1,2,5,9})for(int generation:{0,1,3})for(int seed:{1,7}){
            std::vector<bool> cells;for(int i=0;i<width;++i)cells.push_back((i*i+seed*i+seed)%5<2);
            auto s=compile(code,"{\"cells\":"+cells_json(cells)+",\"steps\":"+std::to_string(generation)+"}");
            auto r=Machine(s).run("batch",20000);
            check(r.status=="COMPLETE"&&export_json(s,r.value)==cells_json(reference(cells,generation)),"CA oracle mismatch");++cases;
        }
        check(cases==30,"case count");
        for(const auto& input:{"{\"cells\":[true],\"steps\":-1}","{\"cells\":[\"x\"],\"steps\":1}","{\"cells\":4,\"steps\":1}"}){
            auto s=compile(code,input);check(Machine(s).run().status=="ERROR","invalid application input accepted");}
    });
    test("strict UTF-8, corrupted history, value cycles and bounded file reads",[]{
        for(const auto& bad:{std::string("\x80"),std::string("\xc0\x80"),std::string("\xed\xa0\x80"),std::string("\xf4\x90\x80\x80")}){
            Space s;rejects([&]{import_json(s,"\""+bad+"\"");});rejects([&]{compile("出力は文「"+bad+"」。");});}
        auto s=compile("「答え」は数「2」と数「3」を足す。\n出力は「答え」。");Machine(s).run();
        Id history=s.ref(s.root,"履歴");s.text(history,"同時に有効","not_a_number");rejects([&]{s.validate();});
        Space cyclic;cyclic.root=cyclic.add("資料空間");Id v=structural_compute(cyclic,"十字を作る",{cyclic.integer(0)});cyclic.link(cyclic.root,"資料",v);
        cyclic.at(cyclic.ref(v,"本体")).arms[0].faces[0].ref=v;rejects([&]{cyclic.validate();});
        {std::ofstream f("structure-limit.txt");f<<"123456789";}rejects([&]{read_file("structure-limit.txt",8);});check(read_file("structure-limit.txt",9)=="123456789","exact file limit");
        {std::ofstream f("structure-limit.txt");f<<"CROSS-IMAGE-1 0 100000\n";}rejects([&]{Space::load("structure-limit.txt");});
    });
    test("structural allocation failures roll back the complete transition",[&]{
        auto s=compile(library+fixture("rotation.cross"));
        for(int step=0;step<100;++step){Machine machine(s);machine.request(machine.output());auto ts=machine.enabled();
            auto it=std::find_if(ts.begin(),ts.end(),[&](const auto& t){return t.rule=="計算"&&s.at(t.node).center=="十字を回す";});
            if(it==ts.end()){machine.run("batch",1);continue;}
            auto full=s;Machine(full).run("batch",1);size_t allocated=full.nodes.size()-s.nodes.size();s.save("structure-test.cross-image");
            const auto before=read_file("structure-test.cross-image");
            for(size_t extra=0;extra<allocated;++extra){auto attempt=s;attempt.limit=attempt.nodes.size()+extra;
                check(Machine(attempt).run("batch",1).status=="NODE_BUDGET","rotation budget ignored");attempt.save("structure-test.cross-image");check(read_file("structure-test.cross-image")==before,"failed rotation changed state");}
            return;
        }throw std::runtime_error("rotation step not found");
    });
    test("compaction preserves recursive results, first-class values and checkpoint resume",[&]{
        for(const auto& fixture_name:{"factorial.cross","concat.cross","rotation.cross"})for(const auto& policy:{"batch","forward","reverse","random"}) {
            auto code=(std::string(fixture_name)=="rotation.cross"?library:"")+fixture(fixture_name);
            const auto input=std::string(fixture_name)=="concat.cross"?"[[1,2],[3,4]]":"null";
            auto full=compile(code,input),small=full;auto expected=run_program(full,policy);
            auto part=run_program(small,policy,17,1,"events","compact",3);
            small.save("structure-test.cross-image");small=Space::load("structure-test.cross-image");
            auto done=run_program(small,policy,10000,1,"events","compact",7);
            check(done.status=="COMPLETE"&&export_json(small,done.value)==export_json(full,expected.value),"compact resume mismatch");
            check(small.ref(small.root,"履歴")==-1&&full.ref(full.root,"履歴")>=0,"history policy not respected");
            check(small.nodes.size()<full.nodes.size()&&done.reclaimed_nodes+part.reclaimed_nodes>0,"no collection");
        }
        Space values;values.root=values.add("計算空間");Id old=structural_compute(values,"十字を作る",{values.integer(1)});
        Id next=put(values,old,"+x/辺/北東",values.integer(8));Id tail=values.add("空列");
        for(Id value:{next,old}){Id cell=values.add("列");values.link(cell,"先頭",value);values.link(cell,"残り",tail);tail=cell;}
        values.link(values.root,"実行",tail);auto expected=export_json(values,tail);compact_space(values);
        check(export_json(values,values.ref(values.root,"実行"))==expected,"live old/new structural values not preserved");
    });
    test("128-cell, 3-generation application completes under the same 100000-node ceiling",[&]{
        std::vector<bool> cells(128);for(size_t i=0;i<cells.size();++i)cells[i]=i%7==3;
        auto s=compile(library+fixture("rule90.cross"),"{\"cells\":"+cells_json(cells)+",\"steps\":3}");
        auto result=run_program(s,"batch",60000,1,"events","compact");
        check(result.status=="COMPLETE"&&export_json(s,result.value)==cells_json(reference(cells,3)),"large CA did not complete correctly");
        check(result.peak_nodes<100000&&result.reclaimed_nodes>100000&&s.nodes.size()<2000,"collection failed to bound retained nodes");
    });
    std::filesystem::remove("structure-test.cross-image");std::filesystem::remove("structure-limit.txt");
    std::cout<<"STRUCTURE RESULT "<<passed<<" passed, "<<failed<<" failed\n";return failed?1:0;
}
