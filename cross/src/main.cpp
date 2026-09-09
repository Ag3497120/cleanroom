#include "cross.hpp"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>

using namespace cross;
namespace {
void output(const std::string& text,const std::string& path){if(path.empty())std::cout<<text<<'\n';else{auto parent=std::filesystem::path(path).parent_path();if(!parent.empty())std::filesystem::create_directories(parent);std::ofstream f(path);if(!f)throw std::runtime_error("出力先を開けません");f<<text<<'\n';}}
size_t natural(const std::string& value){if(value.empty()||value.find_first_not_of("0123456789")!=std::string::npos)throw std::runtime_error("予算は非負整数です");return std::stoull(value);}
void save(Space& space,const std::string& path){auto parent=std::filesystem::path(path).parent_path();if(!parent.empty())std::filesystem::create_directories(parent);space.save(path);}
}
int main(int argc,char** argv){try{
    if(argc<3){std::cout<<".cross 言語 / 六腕・面・辺・頂点の局所計算\n"
        <<"cross run FILE.cross [--meaning DEFINITIONS.cross] [--input DATA.json] [--policy batch|forward|reverse|random [--scheduler events|scan]]\n"
        <<"cross compile FILE.cross --out FILE.cross-image\n"
        <<"cross run FILE.cross-image [--steps 10000] [--save CHECKPOINT.cross-image]\n"
        <<"cross import DATA.json --out DATA.cross-image\n"
        <<"cross export DATA.cross-image [--out DATA.json]\n"
        <<"cross inspect FILE.cross-image [--out TRACE.json]\n"
        <<"run options: --memory full|compact --slice 256 (compact discards history)\n";return argc==1?0:2;}
    std::string command=argv[1],path=argv[2];std::map<std::string,std::string> flags;std::vector<std::string> meaning_files;
    for(int i=3;i<argc;i+=2){if(i+1>=argc)throw std::runtime_error("オプションの値がありません");std::string key=argv[i];
        if(key!="--out"&&key!="--input"&&key!="--meaning"&&key!="--policy"&&key!="--steps"&&key!="--save"&&key!="--max-nodes"&&key!="--seed"&&key!="--scheduler"&&key!="--memory"&&key!="--slice")throw std::runtime_error("未知のオプション: "+key);flags[key]=argv[i+1];if(key=="--meaning")meaning_files.push_back(argv[i+1]);}
    size_t budget=flags.count("--max-nodes")?natural(flags["--max-nodes"]):100000;
    std::string input=flags.count("--input")?read_file(flags["--input"]):"null";
    const auto source_text=[&]{std::string source;for(const auto& file:meaning_files)source+=read_file(file,1024*1024)+"\n";return source+read_file(path,1024*1024);};
    if(command=="compile"){
        if(flags["--out"].empty())throw std::runtime_error("--out が必要です");auto s=compile(source_text(),input,budget);save(s,flags["--out"]);
        output("{\"saved\":"+quote_json(flags["--out"])+",\"nodes\":"+std::to_string(s.nodes.size())+"}","");
    }else if(command=="import"){
        if(flags["--out"].empty())throw std::runtime_error("--out が必要です");Space s;s.limit=budget;s.root=s.add("資料空間");Id data=import_json(s,read_file(path));s.link(s.root,"資料",data);save(s,flags["--out"]);output("{\"saved\":"+quote_json(flags["--out"])+"}","");
    }else if(command=="run"){
        const bool source=std::filesystem::path(path).extension()==".cross";
        if(!source&&(flags.count("--input")||flags.count("--meaning")))throw std::runtime_error("保存済み構造の入力と意味は不変です。変更時は再変換してください");
        auto s=source?compile(source_text(),input,budget):Space::load(path,budget);
        auto r=run_program(s,flags.count("--policy")?flags["--policy"]:"batch",flags.count("--steps")?natural(flags["--steps"]):10000,flags.count("--seed")?natural(flags["--seed"]):1,flags.count("--scheduler")?flags["--scheduler"]:"events",flags.count("--memory")?flags["--memory"]:"full",flags.count("--slice")?natural(flags["--slice"]):256);
        if(flags.count("--save"))save(s,flags["--save"]);output(report_json(s,r),flags["--out"]);return r.status=="COMPLETE"?0:1;
    }else if(command=="export"){
        auto s=Space::load(path,budget);Id value=s.at(s.root).center=="資料空間"?s.ref(s.root,"資料"):result(s,s.ref(s.root,"実行"));
        if(value<0)throw std::runtime_error("結果がまだありません");output(export_json(s,value),flags["--out"]);
    }else if(command=="inspect"){
        auto s=Space::load(path,budget);std::map<std::string,size_t> centers;for(const auto& n:s.nodes)++centers[n.center];
        std::ostringstream out;out<<"{\"nodes\":"<<s.nodes.size()<<",\"arms_per_node\":6,\"faces_per_arm\":4,\"edges_per_arm\":4,\"vertices_per_arm\":4,\"centers\":{";
        bool first=true;for(const auto& [c,count]:centers){if(!first)out<<',';first=false;out<<quote_json(c)<<':'<<count;}out<<"},\"history\":[";
        Id h=s.ref(s.root,"履歴");std::vector<Id> history;std::set<Id> visited;while(h>=0){if(!visited.insert(h).second)throw std::runtime_error("履歴の循環です");history.push_back(h);h=s.ref(h,"前の観測");}
        first=true;for(auto i=history.rbegin();i!=history.rend();++i){if(!first)out<<',';first=false;out<<"{\"enabled\":"<<s.text(*i,"同時に有効")<<",\"events\":[";bool event_first=true;
            for(Id e:s.items(s.ref(*i,"変化"))){if(!event_first)out<<',';event_first=false;out<<"{\"rule\":"<<quote_json(s.text(e,"規則"))<<",\"center\":"<<quote_json(s.at(s.ref(e,"対象")).center)<<",\"node\":"<<s.ref(e,"対象")<<'}';}out<<"]}";}out<<"]}";output(out.str(),flags["--out"]);
    }else throw std::runtime_error("未知のコマンドです");
    return 0;
}catch(const std::exception& error){std::cerr<<"{\"error\":"<<quote_json(error.what())<<"}\n";return 2;}}
