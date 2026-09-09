#pragma once
#include "cross.hpp"
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <random>

using namespace cross;
void check(bool ok,const std::string& text){if(!ok)throw std::runtime_error(text);}
void rejects(const std::function<void()>& f){bool threw=false;try{f();}catch(const std::exception&){threw=true;}check(threw,"not rejected");}
std::string fixture(const std::string& f){return read_file(std::string(EXAMPLE_DIR)+"/"+f);}
std::string source(const std::string& body=""){
    auto text=fixture("grid-stencil.cross");
    if(!body.empty()){
        auto start=text.find("計画「局所規則」は"),end=text.find("計画を終える。",start)+std::string("計画を終える。").size();
        text.replace(start,end-start,"計画「局所規則」は「近傍」を受け取る。\n"+body+"\n返すのは「答え」。\n計画を終える。");
    }
    return fixture("../stdlib/structure.cross")+"\n"+fixture("../stdlib/grid.cross")+"\n"+text;
}
const std::string shift="「答え」は「近傍」の場所文「+x/面/北」の値。";
const std::string rotated="「回転」は「近傍」を軸文「+z」で数「1」回まわした十字。\n「答え」は「回転」の場所文「+y/面/北」の値。";
const std::string xor_rule="「左」は「近傍」の場所文「-x/面/北」の値。\n「右」は「近傍」の場所文「+x/面/北」の値。\n「同じ」は「左」と「右」が等しいか。\n「答え」は「同じ」なら偽、そうでなければ真を選ぶ。";
std::string array_json(const std::vector<int64_t>& v,bool boolean=false){std::string out="[";for(auto x:v){if(out!="[")out+=",";out+=boolean?(x?"true":"false"):std::to_string(x);}return out+"]";}
std::string input(std::array<int,3> dims,const std::vector<int64_t>& v,int steps,bool periodic,int outside=0,bool boolean=false){
    return "{\"shape\":["+std::to_string(dims[0])+","+std::to_string(dims[1])+","+std::to_string(dims[2])+"],\"cells\":"+array_json(v,boolean)+",\"steps\":"+std::to_string(steps)+",\"boundary\":"+quote_json(periodic?"周期":"固定")+",\"outside\":"+(boolean?(outside?"true":"false"):std::to_string(outside))+"}";
}
std::vector<int64_t> oracle(std::array<int,3> d,std::vector<int64_t> cells,int steps,bool periodic,int outside,const std::string& rule){
    auto get=[&](const std::vector<int64_t>& old,int x,int y,int z){
        if(periodic){x=(x+d[0])%d[0];y=(y+d[1])%d[1];z=(z+d[2])%d[2];}
        if(x<0||y<0||z<0||x>=d[0]||y>=d[1]||z>=d[2])return static_cast<int64_t>(outside);
        return old.at(static_cast<size_t>((z*d[1]+y)*d[0]+x));
    };
    for(int step=0;step<steps;++step){auto next=cells;
        for(int z=0;z<d[2];++z)for(int y=0;y<d[1];++y)for(int x=0;x<d[0];++x){
            int64_t n=0;
            if(rule=="shift")n=get(cells,x+1,y,z);
            else if(rule=="xor")n=get(cells,x-1,y,z)!=get(cells,x+1,y,z);
            else n=get(cells,x+1,y,z)+get(cells,x-1,y,z)+get(cells,x,y+1,z)+get(cells,x,y-1,z)+get(cells,x,y,z+1)+get(cells,x,y,z-1);
            next.at(static_cast<size_t>((z*d[1]+y)*d[0]+x))=n;
        }cells=std::move(next);
    }return cells;
}
void same(const Space& a,const Space& b){
    check(a.root==b.root&&a.nodes.size()==b.nodes.size(),"state size");
    for(size_t i=0;i<a.nodes.size();++i){check(a.nodes[i].center==b.nodes[i].center,"center");for(size_t j=0;j<6;++j){const auto& x=a.nodes[i].arms[j];const auto& y=b.nodes[i].arms[j];
        for(auto pair:{std::make_pair(&x.faces,&y.faces),std::make_pair(&x.edges,&y.edges),std::make_pair(&x.vertices,&y.vertices)})for(size_t k=0;k<4;++k)
            check((*pair.first)[k].text==(*pair.second)[k].text&&(*pair.first)[k].ref==(*pair.second)[k].ref,"slot mismatch");}}
}
