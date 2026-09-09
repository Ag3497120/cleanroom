// A diagnostic comparison, not a matched hardware-performance experiment.
// The flat controls omit cross-port delivery and the persistent execution log.
#include "cross.hpp"
#include <algorithm>
#include <chrono>
#include <fstream>
#include <functional>
#include <iostream>
#include <numeric>

using namespace cross;
struct Op {Id id;std::string name;std::vector<Id> inputs;};
struct Flat {std::map<Id,int64_t> literals;std::vector<Op> code;Id output;};
Flat flatten(const Space& space){
    Flat f;f.output=space.ref(space.root,"実行");std::map<Id,int> color;
    std::function<void(Id)> visit=[&](Id i){
        if(color[i]==2)return;if(color[i]==1)throw std::runtime_error("benchmark cycle");color[i]=1;
        const auto node=space.at(i);if(node.center=="整数")f.literals[i]=std::stoll(space.text(i,"値"));
        else{const auto op=operation(space,node.center);if(op!="参照"&&op!="足す"&&op!="掛ける")throw std::runtime_error("benchmark op");std::vector<Id> args;
             for(const auto& role:roles(op)){Id x=node.port(role).edges[0].ref;visit(x);args.push_back(x);}f.code.push_back({i,op,args});}color[i]=2;
    };visit(f.output);return f;
}
int64_t arithmetic(const Op& op,const std::map<Id,int64_t>& values){
    if(op.name=="参照")return values.at(op.inputs[0]);auto a=values.at(op.inputs[0]),b=values.at(op.inputs[1]);return op.name=="足す"?a+b:a*b;
}
struct Run {int64_t value;size_t steps,width;};
Run pc_run(const Flat& f){auto values=f.literals;size_t pc=0;while(pc<f.code.size()){const auto& op=f.code[pc];values[op.id]=arithmetic(op,values);++pc;}return {values.at(f.output),pc,1};}
Run flow_run(const Flat& f){auto values=f.literals;size_t stages=0,width=0;while(!values.count(f.output)){
    std::vector<std::pair<Id,int64_t>> ready;for(const auto& op:f.code){if(values.count(op.id))continue;bool all=true;for(Id x:op.inputs)all&=values.count(x)!=0;if(all)ready.push_back({op.id,arithmetic(op,values)});}
    if(ready.empty())throw std::runtime_error("benchmark stuck");for(const auto& [id,v]:ready)values[id]=v;width=std::max(width,ready.size());++stages;
}return {values.at(f.output),stages,width};}
std::string program(size_t width,bool chain){
    std::string text="プロジェクト「方式比較」。\n";std::vector<std::string> names;
    for(size_t i=0;i<width;++i){std::string name="枝"+std::to_string(i);text+="「"+name+"」は数「"+std::to_string(i+1)+"」と数「2」を掛ける。\n";names.push_back(name);}
    size_t next=0;
    while(names.size()>1){std::vector<std::string> upper;for(size_t i=0;i<names.size();){if(i+1==names.size()){upper.push_back(names[i]);break;}std::string name="結合"+std::to_string(next++);text+="「"+name+"」は「"+names[i]+"」と「"+names[i+1]+"」を足す。\n";upper.push_back(name);i+=2;if(chain){upper.insert(upper.end(),names.begin()+static_cast<long>(i),names.end());break;}}names=upper;}
    text+="出力は「"+names[0]+"」。\n";return text;
}
template<class F> double median(F function){std::vector<double> samples;for(int i=0;i<5;++i){auto start=std::chrono::steady_clock::now();function();samples.push_back(std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count());}std::sort(samples.begin(),samples.end());return samples[2];}
int main(int argc,char** argv){try{
    std::string out="{\"scope\":\"synthetic arithmetic; host simulation, not hardware or AI accuracy\",\"timings_are_fully_matched\":false,\"cases\":[";bool first=true;
    for(bool chain:{false,true})for(size_t width:{4,8,16}){
        auto space=compile(program(width,chain));auto flat=flatten(space);auto pc=pc_run(flat),flow=flow_run(flat);auto copy=space;auto cr=Machine(copy).run();
        int64_t expected=static_cast<int64_t>(width*(width+1));if(pc.value!=expected||flow.value!=expected||cr.status!="COMPLETE"||export_json(copy,cr.value)!=std::to_string(expected))throw std::runtime_error("differential result mismatch");
        double pc_ms=median([&]{volatile auto v=pc_run(flat).value;(void)v;}),flow_ms=median([&]{volatile auto v=flow_run(flat).value;(void)v;});
        double cross_ms=median([&]{auto s=space;auto r=Machine(s).run();if(r.status!="COMPLETE")throw std::runtime_error("run failed");});
        if(!first)out+=",";first=false;out+="{\"shape\":"+quote_json(chain?"chain":"balanced")+",\"width\":"+std::to_string(width)+",\"expected\":"+std::to_string(expected)
            +",\"all_equal\":true,\"pc_instructions\":"+std::to_string(pc.steps)+",\"flat_dataflow_stages\":"+std::to_string(flow.steps)+",\"flat_max_enabled\":"+std::to_string(flow.width)
            +",\"cross_stages_including_delivery\":"+std::to_string(cr.steps)+",\"cross_max_enabled\":"+std::to_string(cr.max_enabled)+",\"initial_cross_nodes\":"+std::to_string(space.nodes.size())
            +",\"final_cross_nodes_including_log\":"+std::to_string(copy.nodes.size())+",\"median_ms\":{\"pc\":"+std::to_string(pc_ms)+",\"flat_dataflow\":"+std::to_string(flow_ms)+",\"cross_with_log_and_copy\":"+std::to_string(cross_ms)+"}}";
    }
    out+="],\"conclusion\":\"No cross-geometry speed advantage is established. Dataflow parallelism exists in the flat control too.\"}";
    if(argc>1){std::ofstream f(argv[1]);f<<out<<'\n';}std::cout<<out<<'\n';return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
