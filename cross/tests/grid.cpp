#include "grid_support.hpp"
int main(){int passed=0,failed=0;auto test=[&](const char* name,const std::function<void()>& f){try{f();++passed;std::cout<<"PASS "<<name<<'\n';}catch(const std::exception& e){++failed;std::cout<<"FAIL "<<name<<": "<<e.what()<<'\n';}};
    test("1D/2D/3D fields, fixed/periodic edges and user-written sum: 48 oracle cases",[]{
        std::mt19937 rng(27);auto code=source();int count=0;
        for(auto dims:{std::array<int,3>{1,1,1},{7,1,1},{3,4,1},{2,3,2}})for(bool periodic:{false,true})for(int steps:{0,1,3})for(int seed=0;seed<2;++seed){
            std::vector<int64_t> cells(dims[0]*dims[1]*dims[2]);for(auto& value:cells)value=static_cast<int>(rng()%11)-5;
            auto s=compile(code,input(dims,cells,steps,periodic,-2));auto r=run_program(s,"batch",20000,1,"events","compact",31);
            check(r.status=="COMPLETE"&&export_json(s,r.value)==array_json(oracle(dims,cells,steps,periodic,-2,"sum")),"sum oracle");++count;
        }check(count==48,"case count");
    });
    test("local plan replacement and rotation change the rule without host changes",[]{
        for(const auto& body:{shift,rotated})for(bool periodic:{false,true}){
            std::array<int,3> dims{4,3,2};std::vector<int64_t> cells(24);for(size_t i=0;i<cells.size();++i)cells[i]=i+1;
            auto s=compile(source(body),input(dims,cells,2,periodic,-3));auto r=run_program(s,"batch",10000);
            check(r.status=="COMPLETE"&&export_json(s,r.value)==array_json(oracle(dims,cells,2,periodic,-3,"shift")),"shift oracle");
        }
    });
    test("six-neighbor topology changes results when shape or boundary changes",[]{
        std::vector<int64_t> cells{1,2,3,4,5,6};std::set<std::string> outputs;
        for(auto d:{std::array<int,3>{6,1,1},{3,2,1},{1,2,3}})for(bool periodic:{false,true}){
            auto s=compile(source(shift),input(d,cells,1,periodic,0));auto r=Machine(s).run();check(r.status=="COMPLETE","shape complete");outputs.insert(export_json(s,r.value));
        }check(outputs.size()>=5,"geometry ignored");
    });
    test("events/scan and four selection policies agree in full and compact",[]{
        auto code=source();auto start=compile(code,input({3,2,2},{1,2,3,4,5,6,7,8,9,10,11,12},2,true));
        auto expected=array_json(oracle({3,2,2},{1,2,3,4,5,6,7,8,9,10,11,12},2,true,0,"sum"));
        for(const auto& policy:{"batch","forward","reverse","random"})for(const auto& memory:{"full","compact"}){
            auto a=start,b=start;auto ra=run_program(a,policy,30000,29,"events",memory,37),rb=run_program(b,policy,30000,29,"scan",memory,37);
            check(ra.status=="COMPLETE"&&rb.status=="COMPLETE"&&export_json(a,ra.value)==expected&&export_json(b,rb.value)==expected,"policy result");same(a,b);a.validate();
        }
    });
    test("expanded cells execute as independent demand-driven plans",[]{
        std::vector<int64_t> cells(64,1);auto s=compile(source(shift),input({4,4,4},cells,1,true));auto r=Machine(s).run();
        check(r.status=="COMPLETE"&&r.max_enabled>=64,"cell execution serialized");
        check(r.grid_expansions==1&&r.expanded_cells==64&&r.neighbor_slots==384,"bulk work counters");
        size_t calls=0;for(const auto& n:s.nodes)if(n.center=="呼ぶ"&&n.port("展開").edges[0].ref>=0)++calls;
        check(calls>=64,"local plans not evaluated");
    });
    test("grid expansion and join checkpoints survive relocation and reload",[]{
        auto start=compile(source(shift),input({4,2,1},{1,2,3,4,5,6,7,8},2,true));
        for(size_t cut:{0,70,90,100,110,120,140,160}){
            auto s=start;run_program(s,"batch",cut,1,"events","compact",13);s.save("grid-checkpoint.cross-image");s=Space::load("grid-checkpoint.cross-image");
            auto r=run_program(s,"random",20000,71,"scan","compact",17);
            check(r.status=="COMPLETE"&&export_json(s,r.value)==array_json(oracle({4,2,1},{1,2,3,4,5,6,7,8},2,true,0,"shift")),"resume");
        }
    });
    test("allocation failure at every grid-expansion allocation rolls back and reports actual peak",[]{
        auto start=compile(source(shift),input({2,1,1},{1,2},1,true));
        for(int step=0;step<200;++step){Machine m(start);m.request(m.output());auto ts=m.enabled();bool expansion=std::any_of(ts.begin(),ts.end(),[](const auto& t){return t.rule=="近傍を展開";});
            if(!expansion){m.run("batch",1);continue;}
            auto full=start;Machine(full).run("batch",1);size_t allocation=full.nodes.size()-start.nodes.size();
            for(size_t extra=0;extra<allocation;++extra){auto s=start;s.limit=s.nodes.size()+extra;auto r=run_program(s,"batch",1);
                check(r.status=="NODE_BUDGET"&&r.peak_nodes==s.limit&&r.grid_expansions==0,"peak or rollback counters");same(s,start);s.limit=100000;check(run_program(s).status=="COMPLETE","retry");}
            return;
        }throw std::runtime_error("expansion absent");
    });
    test("invalid dimensions, counts and boundary rejected as runtime errors",[]{
        for(const auto& data:{"{\"shape\":[0,1,1],\"cells\":[1],\"steps\":1,\"boundary\":\"周期\",\"outside\":0}","{\"shape\":[2,1,1],\"cells\":[1],\"steps\":1,\"boundary\":\"周期\",\"outside\":0}","{\"shape\":[1,1,1],\"cells\":[1],\"steps\":1,\"boundary\":\"unknown\",\"outside\":0}","{\"shape\":[9223372036854775807,2,2],\"cells\":[1],\"steps\":1,\"boundary\":\"周期\",\"outside\":0}"}){
            auto s=compile(source(shift),data);check(run_program(s).status=="ERROR","invalid grid accepted");
        }
        auto broken=source("「答え」は数「1」を数「0」で割る。");auto s=compile(broken,input({3,1,1},{1,2,3},1,true));check(run_program(s).status=="ERROR","cell error swallowed");
    });
    test("128-cell rule90 for three generations uses the same generic mapper",[]{
        std::array<int,3> dims{128,1,1};std::vector<int64_t> cells(128);for(size_t i=0;i<cells.size();++i)cells[i]=i%7==3;
        for(const auto& memory:{"full","compact"}){
            auto s=compile(source(xor_rule),input(dims,cells,3,true,0,true));auto r=run_program(s,"batch",20000,1,"events",memory);
            check(r.status=="COMPLETE"&&export_json(s,r.value)==array_json(oracle(dims,cells,3,true,0,"xor"),true),"rule90 oracle");
            check(r.grid_expansions==3&&r.expanded_cells==384&&r.neighbor_slots==2304,"compact loses work counters");
        }
    });
    test("completed grid and shared old/new immutable values survive compaction",[]{
        Space s;s.root=s.add("計算空間");auto dimensions=import_json(s,"[2,1,1]"),cells=import_json(s,"[3,4]");auto field=grid_compute(s,"格子を作る",{dimensions,cells,s.string("周期"),s.integer(0)});
        s.link(s.root,"実行",field);auto expected=export_json(s,field);s.save("grid-checkpoint.cross-image");auto loaded=Space::load("grid-checkpoint.cross-image");
        compact_space(loaded);check(export_json(loaded,loaded.ref(loaded.root,"実行"))==expected,"field persistence");
        auto invalid=s;invalid.text(field,"境界","unknown");rejects([&]{invalid.validate();});
        invalid=s;invalid.link(field,"形状",cells);rejects([&]{invalid.validate();});
    });
    std::filesystem::remove("grid-checkpoint.cross-image");std::cout<<"GRID RESULT "<<passed<<" passed, "<<failed<<" failed\n";return failed?1:0;
}
