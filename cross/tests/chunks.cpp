#include "grid_support.hpp"
#include <limits>

std::string chunked(const std::string& body,int64_t width){
    auto code=source(body);auto at=code.find("を適用した格子。");
    check(at!=std::string::npos,"application site");
    code.replace(at,std::string("を適用した格子。").size(),"を最大数「"+std::to_string(width)+"」セルずつ適用した格子。");return code;
}
std::vector<int64_t> direction_oracle(std::array<int,3> d,const std::vector<int64_t>& cells,int axis,int sign,bool periodic){
    std::vector<int64_t> out;
    for(int z=0;z<d[2];++z)for(int y=0;y<d[1];++y)for(int x=0;x<d[0];++x){
        std::array<int,3> p{x,y,z};p[axis]+=sign;
        if(periodic)p[axis]=(p[axis]+d[axis])%d[axis];
        out.push_back(p[axis]<0||p[axis]>=d[axis]?-99:cells.at((p[2]*d[1]+p[1])*d[0]+p[0]));
    }return out;
}
int main(){int passed=0,failed=0;auto test=[&](const char* name,const std::function<void()>& f){try{f();++passed;std::cout<<"PASS "<<name<<'\n';}catch(const std::exception& e){++failed;std::cout<<"FAIL "<<name<<": "<<e.what()<<'\n';}};
    test("chunk widths, shapes, boundaries and generations: 72 sum oracle cases",[]{
        size_t count=0;
        for(auto d:{std::array<int,3>{1,1,1},{7,1,1},{2,3,2}})for(bool periodic:{false,true})for(int generations:{0,1,3})for(int width:{1,3,8,32}){
            std::vector<int64_t> cells(d[0]*d[1]*d[2]);for(size_t i=0;i<cells.size();++i)cells[i]=static_cast<int>(i%7)-3;
            auto s=compile(chunked("",width),input(d,cells,generations,periodic,-2));auto r=run_program(s,"batch",30000,1,"events","compact",29);
            check(r.status=="COMPLETE"&&export_json(s,r.value)==array_json(oracle(d,cells,generations,periodic,-2,"sum")),"sum result");
            check(r.grid_expansions==static_cast<size_t>(generations)&&r.grid_chunks==static_cast<size_t>(generations)*((cells.size()+width-1)/width),"chunk counters");
            check(r.max_chunk_cells<=static_cast<size_t>(width)&&r.expanded_cells==cells.size()*generations,"work bound");++count;
        }check(count==72,"case count");
    });
    test("all six directed ports, asymmetric 3D shape and fixed/periodic boundaries",[]{
        std::array<int,3> d{2,3,4};std::vector<int64_t> cells(24);for(size_t i=0;i<cells.size();++i)cells[i]=11+i*3;
        for(int axis=0;axis<3;++axis)for(int sign:{-1,1})for(bool periodic:{false,true}){
            std::string direction=(sign>0?"+":"-")+std::string(1,"xyz"[axis]);
            auto s=compile(chunked("「答え」は「近傍」の場所文「"+direction+"/面/北」の値。",5),input(d,cells,1,periodic,-99));
            auto r=run_program(s,"batch",10000);check(r.status=="COMPLETE"&&export_json(s,r.value)==array_json(direction_oracle(d,cells,axis,sign,periodic)),"direction oracle");
        }
    });
    test("indexed six-way tree boundaries and signed-64-bit maximum window",[]{
        for(int n:{1,6,7,35,36,37,215,216,217}){
            std::vector<int64_t> cells(n);for(int i=0;i<n;++i)cells[i]=i;
            auto s=compile(chunked(shift,n==1?std::numeric_limits<int64_t>::max():5),input({n,1,1},cells,1,true));
            auto r=run_program(s,"batch",30000,1,"events","compact",97);
            check(r.status=="COMPLETE"&&export_json(s,r.value)==array_json(oracle({n,1,1},cells,1,true,0,"shift")),"tree index");
        }
    });
    test("snapshot of old generation is preserved across chunk boundaries",[]{
        // In-place left-to-right mutation would produce a different answer.
        std::vector<int64_t> cells{1,0,1,1,0,0,0,1,0};
        auto s=compile(chunked(xor_rule,2),input({9,1,1},cells,4,true,0,true));auto r=run_program(s,"batch",30000,1,"events","compact",19);
        check(r.status=="COMPLETE"&&export_json(s,r.value)==array_json(oracle({9,1,1},cells,4,true,0,"xor"),true),"simultaneous old generation");
    });
    test("four policies and two schedulers match result and full state in both memory modes",[]{
        auto start=compile(chunked(shift,2),input({3,2,1},{1,2,3,4,5,6},2,false,-7));auto expected=array_json(oracle({3,2,1},{1,2,3,4,5,6},2,false,-7,"shift"));
        for(const auto& policy:{"batch","forward","reverse","random"})for(const auto& memory:{"full","compact"}){
            auto a=start,b=start;auto ra=run_program(a,policy,20000,7,"events",memory,31),rb=run_program(b,policy,20000,7,"scan",memory,31);
            check(ra.status=="COMPLETE"&&rb.status=="COMPLETE"&&export_json(a,ra.value)==expected&&export_json(b,rb.value)==expected,"selection result");same(a,b);
        }
    });
    test("records, nulls and lists remain first-class cell values",[]{
        auto s=compile(chunked(shift,1),"{\"shape\":[3,1,1],\"cells\":[{\"a\":[1,true]},null,[\"x\"]],\"steps\":2,\"boundary\":\"周期\",\"outside\":null}");
        auto r=run_program(s,"batch",10000,1,"events","compact",11);
        check(r.status=="COMPLETE"&&export_json(s,r.value)=="[[\"x\"],{\"a\":[1,true]},null]","structured cells");
    });
    test("completed prefix and in-flight chunk survive relocation and fresh image load",[]{
        auto s=compile(chunked(shift,2),input({7,1,1},{1,2,3,4,5,6,7},2,true));bool found=false;
        for(int i=0;i<1000;++i){Machine(s).run("batch",1);
            for(size_t j=0;j<s.nodes.size();++j)if(s.nodes[j].center=="格子の分割実行"&&s.ref(static_cast<Id>(j),"展開")>=0){
                Id p=s.nodes[j].port("進行").vertices[0].ref;if(p>=0&&std::stoll(s.text(s.ref(p,"位置"),"値"))>0){found=true;break;}}
            if(found)break;
        }check(found,"no partial chunk");compact_space(s);s.save("chunks-checkpoint.cross-image");
        for(const auto& policy:{"batch","forward","reverse","random"}){
            auto loaded=Space::load("chunks-checkpoint.cross-image");auto r=run_program(loaded,policy,20000,17,"scan","compact",23);
            check(r.status=="COMPLETE"&&export_json(loaded,r.value)=="[3,4,5,6,7,1,2]","chunk resume");
            for(const auto& n:loaded.nodes)check(n.center!="格子の進行"&&n.center!="格子の分割実行","retained continuation");
        }
    });
    test("every allocation in start, expansion and continuation rolls back atomically",[]{
        for(const std::string rule:{"分割近傍を開始","分割近傍を展開","分割近傍を継続"}){
            auto start=compile(chunked(shift,2),input({5,1,1},{1,2,3,4,5},1,true));bool found=false;
            for(int i=0;i<300;++i){Machine m(start);m.request(m.output());auto ts=m.enabled();
                if(std::none_of(ts.begin(),ts.end(),[&](const auto& t){return t.rule==rule;})){m.run("batch",1);continue;}
                auto done=start;Machine(done).run("batch",1);size_t allocations=done.nodes.size()-start.nodes.size();check(allocations>0,"no allocations");
                for(size_t extra=0;extra<allocations;++extra){auto s=start;s.limit=s.nodes.size()+extra;auto r=Machine(s).run("batch",1);
                    check(r.status=="NODE_BUDGET"&&r.peak_nodes==s.limit&&r.grid_expansions==0&&r.grid_chunks==0,"rollback status or accounting");same(s,start);
                    s.limit=100000;check(run_program(s).status=="COMPLETE","rollback retry");}
                found=true;break;
            }check(found,"transition absent: "+rule);
        }
    });
    test("corrupt progress, prefix length and packed cell index are rejected",[]{
        auto s=compile(chunked(shift,2),input({7,1,1},{1,2,3,4,5,6,7},1,true));Id progress=-1;
        for(int step=0;step<300&&progress<0;++step){Machine(s).run("batch",1);for(size_t i=0;i<s.nodes.size();++i)
            if(s.nodes[i].center=="格子の進行"&&s.ref(static_cast<Id>(i),"完了")>=0){progress=static_cast<Id>(i);break;}}
        check(progress>=0,"no prefix");
        for(int value:{-1,0,1,7}){auto broken=s;broken.link(progress,"位置",broken.integer(value));rejects([&]{broken.validate();});}
        auto broken=s;broken.link(progress,"幅",broken.integer(0));rejects([&]{broken.validate();});
        broken=s;Id field=s.ref(progress,"雛形"),root=s.ref(field,"セル");auto& arms=broken.at(root).arms;std::swap(arms[1],arms[2]);
        // Keep old traversal order but move role 1 to role 2: old traversal
        // accepts the same number of cells; indexed lookup must reject the gap.
        int role=broken.at(root).find("1");check(role>=0,"missing second page");broken.at(root).arms[role].faces[0].text="2";
        rejects([&]{broken.validate();});
    });
    test("invalid windows and user-local errors propagate as ERROR",[]{
        for(int width:{0,-1}){auto s=compile(chunked(shift,width),input({3,1,1},{1,2,3},1,true));check(run_program(s).status=="ERROR","bad window accepted");}
        auto s=compile(chunked("「中央」は「近傍」の中央の値。\n「答え」は数「1」を「中央」で割る。",1),input({3,1,1},{1,0,1},1,true));
        auto r=run_program(s,"batch",10000,1,"events","compact",17);check(r.status=="ERROR","later chunk failure lost");
    });
    test("two overlapping mappers share immutable input without sharing progress",[]{
        auto code=source(shift);code.resize(code.find("「更新」は計画"));
        code+="「一」は「格子」の六近傍へ計画「局所規則」を最大数「1」セルずつ適用した格子。\n"
              "「二」は「格子」の六近傍へ計画「局所規則」を最大数「3」セルずつ適用した格子。\n"
              "「一列」は「一」のセル列。\n「二列」は「二」のセル列。\n"
              "「結果の尾」は「二列」と空の列を対にする。\n「答え」は「一列」と「結果の尾」を対にする。\n出力は「答え」。\n";
        auto start=compile(code,input({7,1,1},{1,2,3,4,5,6,7},1,true));
        auto observed=start;bool overlap=false;
        for(int i=0;i<500&&result(observed,observed.ref(observed.root,"実行"))<0;++i){
            Machine(observed).run("batch",1);size_t live=0;
            for(size_t j=0;j<observed.nodes.size();++j)if(observed.nodes[j].center=="格子の分割実行"&&result(observed,static_cast<Id>(j))<0)++live;
            overlap|=live>=2;
        }check(overlap,"mappers did not overlap");
        for(const auto& policy:{"batch","forward","reverse","random"}){
            auto s=start;auto r=run_program(s,policy,20000,9,"events","compact",17);
            check(r.status=="COMPLETE"&&export_json(s,r.value)=="[[2,3,4,5,6,7,1],[2,3,4,5,6,7,1]]","shared input changed");
            check(r.grid_expansions==2&&r.grid_chunks==10&&r.expanded_cells==14,"independent progress counters");
        }
    });
    test("1024 cells finish within 6000 nodes where 0.4 cannot expand",[]{
        std::vector<int64_t> cells(1024);for(size_t i=0;i<cells.size();++i)cells[i]=i;
        auto s=compile(chunked(shift,8),input({1024,1,1},cells,1,true),6000);auto r=run_program(s,"batch",60000,1,"events","compact");
        check(r.status=="COMPLETE"&&export_json(s,r.value)==array_json(oracle({1024,1,1},cells,1,true,0,"shift")),"bounded run");
        check(r.grid_chunks==128&&r.max_chunk_cells==8&&r.expanded_cells==1024&&r.peak_nodes<=6000,"bounded work counts");
    });
    std::filesystem::remove("chunks-checkpoint.cross-image");std::cout<<"CHUNKS RESULT "<<passed<<" passed, "<<failed<<" failed\n";return failed?1:0;
}
