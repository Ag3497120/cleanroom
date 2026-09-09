#include "cross.hpp"
#include <algorithm>
#include <limits>

namespace cross {
namespace {
std::vector<Id> list_items(const Space& s,Id list){
    std::vector<Id> out;std::set<Id> seen;
    while(s.at(list).center=="列"){
        if(!seen.insert(list).second)throw std::runtime_error("格子入力の列が循環しています");
        out.push_back(s.ref(list,"先頭"));list=s.ref(list,"残り");
    }
    if(s.at(list).center!="空列")throw std::runtime_error("格子入力には列が必要です");
    return out;
}
std::array<size_t,3> shape(const Space& s,Id value){
    auto dims=list_items(s,value);
    if(dims.size()!=3)throw std::runtime_error("形状は正の整数三つ [x,y,z] です");
    std::array<size_t,3> out{};size_t volume=1;
    for(size_t i=0;i<3;++i){
        if(s.at(dims[i]).center!="整数")throw std::runtime_error("形状には整数が必要です");
        auto n=std::stoll(s.text(dims[i],"値"));
        if(n<=0||static_cast<uint64_t>(n)>static_cast<uint64_t>(std::numeric_limits<Id>::max())||
           volume>static_cast<size_t>(std::numeric_limits<Id>::max())/static_cast<size_t>(n))
            throw std::runtime_error("格子の形状が範囲外です");
        out[i]=static_cast<size_t>(n);volume*=out[i];
    }
    return out;
}
size_t volume(const std::array<size_t,3>& d){return d[0]*d[1]*d[2];}
size_t capacity(size_t count){size_t c=6;while(c<count)c*=6;return c;}
// Space::sequence emits a packed six-way tree. Check the shape before indexed
// access; a merely traversable but sparse snapshot must not change cell order.
void packed_cells(const Space& s,Id root,size_t count){
    struct Part{Id id;size_t count,capacity;};
    std::vector<Part> todo{{root,count,capacity(count)}};
    while(!todo.empty()){
        auto p=todo.back();todo.pop_back();bool leaf=p.capacity==6;
        if(s.at(p.id).center!=(leaf?"束の葉":"束の枝"))throw std::runtime_error("格子のセル索引の深さが不正です");
        const size_t span=leaf?1:p.capacity/6;
        for(size_t i=0;i<6;++i){
            Id child=s.ref(p.id,std::to_string(i));size_t length=p.count>i*span?std::min(span,p.count-i*span):0;
            if((length==0)!=(child<0))throw std::runtime_error("格子のセル索引に空隙があります");
            if(length&&!leaf)todo.push_back({child,length,span});
        }
    }
}
Id indexed_cell(const Space& s,Id field,size_t index,size_t count){
    if(index>=count)throw std::runtime_error("格子のセル位置が範囲外です");
    Id page=s.ref(field,"セル");size_t span=capacity(count);
    while(span>6){span/=6;page=s.ref(page,std::to_string(index/span));index%=span;}
    return s.ref(page,std::to_string(index));
}
void require_value(const Space& s,Id id){
    if(!is_value(s.at(id).center))throw std::runtime_error("格子のセルは値でなければなりません");
}
void require_field(const Space& s,Id id){
    if(s.at(id).center!="格子の値")throw std::runtime_error("格子の値が必要です");
}
Id make_field(Space& s,Id dimensions,const std::vector<Id>& cells,const std::string& boundary,Id outside){
    auto dims=shape(s,dimensions);
    if(volume(dims)!=cells.size())throw std::runtime_error("形状の体積とセル数が一致しません");
    if(boundary!="周期"&&boundary!="固定")throw std::runtime_error("境界は 周期 または 固定 です");
    require_value(s,outside);for(Id cell:cells)require_value(s,cell);
    Id bundle=s.sequence(cells),field=s.add("格子の値");
    s.link(field,"形状",dimensions);s.link(field,"セル",bundle);
    s.text(field,"境界",boundary);s.link(field,"外側",outside);return field;
}
Id instruction(Space& s,const std::string& name,const std::vector<Id>& args){
    auto names=roles(name);if(args.size()!=names.size())throw std::runtime_error("内部の格子命令の引数数が違います");
    Id id=s.add(name);
    for(size_t i=0;i<args.size();++i)s.link(id,names[i],args[i]);return id;
}
std::vector<Id> bundle_items(const Space& s,Id root,size_t maximum){
    std::vector<std::pair<Id,bool>> pending{{root,false}};std::vector<Id> out;std::set<Id> active;
    while(!pending.empty()){
        auto [id,exit]=pending.back();pending.pop_back();
        if(exit){active.erase(id);continue;}
        if(!active.insert(id).second)throw std::runtime_error("セル束が循環しています");
        if(s.at(id).center!="セル束")throw std::runtime_error("セル束が必要です");
        pending.emplace_back(id,true);
        if(s.ref(id,"値")>=0){
            if(out.size()==maximum)throw std::runtime_error("セル束が格子の体積を超えています");
            out.push_back(s.ref(id,"値"));
        }else{pending.emplace_back(s.ref(id,"右"),false);pending.emplace_back(s.ref(id,"左"),false);}
    }
    return out;
}
}
std::vector<std::string> grid_roles(const std::string& op){
    if(op=="格子を作る")return {"形状","セル","境界","外側"};
    if(op=="格子のセル"||op=="格子の形状")return {"対象"};
    if(op=="格子へ適用")return {"対象","計画"};
    if(op=="格子へ分割適用")return {"対象","計画","幅"};
    if(op=="格子の分割実行")return {"対象","計画","進行"};
    // Binary joins avoid an unbounded input port or sequential guest loop.
    if(op=="セルを包む")return {"値"};
    if(op=="セル束を結ぶ")return {"左","右"};
    if(op=="格子を確定")return {"雛形","束"};
    return {};
}
std::vector<Id> grid_cells(const Space& s,Id field){require_field(s,field);return s.items(s.ref(field,"セル"));}
Id grid_compute(Space& s,const std::string& op,const std::vector<Id>& v){
    if(op=="格子を作る"){
        if(s.at(v[2]).center!="文章")throw std::runtime_error("境界には文章が必要です");
        return make_field(s,v[0],list_items(s,v[1]),s.text(v[2],"値"),v[3]);
    }
    if(op=="格子の形状"){require_field(s,v[0]);return s.ref(v[0],"形状");}
    if(op=="格子のセル"){
        auto cells=grid_cells(s,v[0]);Id list=s.add("空列");
        for(auto i=cells.rbegin();i!=cells.rend();++i){Id n=s.add("列");s.link(n,"先頭",*i);s.link(n,"残り",list);list=n;}return list;
    }
    if(op=="セルを包む"){require_value(s,v[0]);Id b=s.add("セル束");s.link(b,"値",v[0]);return b;}
    if(op=="セル束を結ぶ"){
        if(s.at(v[0]).center!="セル束"||s.at(v[1]).center!="セル束")throw std::runtime_error("結合入力はセル束です");
        Id b=s.add("セル束");s.link(b,"左",v[0]);s.link(b,"右",v[1]);return b;
    }
    if(op=="格子を確定"){
        require_field(s,v[0]);return make_field(s,s.ref(v[0],"形状"),bundle_items(s,v[1],volume(shape(s,s.ref(v[0],"形状")))),s.text(v[0],"境界"),s.ref(v[0],"外側"));
    }
    throw std::runtime_error("未定義の格子演算です");
}
Id expand_grid(Space& s,Id field,Id plan){
    require_field(s,field);validate_grid_value(s,field);
    if(s.at(plan).center!="計画の値")throw std::runtime_error("格子への適用には計画が必要です");
    const auto dims=shape(s,s.ref(field,"形状"));const auto cells=grid_cells(s,field);
    const bool periodic=s.text(field,"境界")=="周期";const Id outside=s.ref(field,"外側");
    std::vector<Id> level;level.reserve(cells.size());
    for(size_t index=0;index<cells.size();++index){
        const std::array<size_t,3> position{index%dims[0],(index/dims[0])%dims[1],index/(dims[0]*dims[1])};
        Id data=s.add("六腕の配置");
        for(size_t direction=0;direction<6;++direction){
            const size_t axis=direction/2;const bool positive=direction%2==0;
            auto adjacent=position;Id neighbor=outside;
            const bool edge=positive?position[axis]+1==dims[axis]:position[axis]==0;
            if(!edge||periodic){
                adjacent[axis]=positive?(position[axis]+1)%dims[axis]:(position[axis]+dims[axis]-1)%dims[axis];
                neighbor=cells[adjacent[0]+dims[0]*(adjacent[1]+dims[1]*adjacent[2])];
            }
            s.at(data).arms[direction].faces[0].ref=neighbor;
        }
        Id local=s.add("十字の値");s.link(local,"中央",cells[index]);s.link(local,"本体",data);
        Id call=instruction(s,"呼ぶ",{plan,local});
        level.push_back(instruction(s,"セルを包む",{call}));
    }
    while(level.size()>1){
        std::vector<Id> upper;
        for(size_t i=0;i<level.size();i+=2)upper.push_back(i+1==level.size()?level[i]:instruction(s,"セル束を結ぶ",{level[i],level[i+1]}));
        level=std::move(upper);
    }
    return instruction(s,"格子を確定",{field,level.at(0)});
}
void validate_grid_value(const Space& s,Id value){
    if(s.at(value).center=="格子の進行"){
        Id field=s.ref(value,"雛形");require_field(s,field);
        Id position=s.ref(value,"位置"),width=s.ref(value,"幅");
        if(s.at(position).center!="整数"||s.at(width).center!="整数")throw std::runtime_error("格子の進行位置と幅は整数です");
        auto start=std::stoll(s.text(position,"値")),chunk=std::stoll(s.text(width,"値"));
        if(start<0||static_cast<uint64_t>(start)>=volume(shape(s,s.ref(field,"形状")))||chunk<=0)throw std::runtime_error("格子の進行範囲が不正です");
        Id prefix=s.ref(value,"完了");
        if(start==0){if(prefix>=0)throw std::runtime_error("開始前に格子の完了値があります");}
        else if(prefix<0||bundle_items(s,prefix,static_cast<size_t>(start)).size()!=static_cast<size_t>(start))throw std::runtime_error("格子の進行位置と完了セル数が違います");
        return;
    }
    if(s.at(value).center=="セル束"){
        Id leaf=s.ref(value,"値"),left=s.ref(value,"左"),right=s.ref(value,"右");
        if(leaf>=0){if(left>=0||right>=0)throw std::runtime_error("セル束の葉に枝があります");require_value(s,leaf);}
        else if(s.at(left).center!="セル束"||s.at(right).center!="セル束")throw std::runtime_error("セル束の枝が不正です");
        return;
    }
    require_field(s,value);const auto dims=shape(s,s.ref(value,"形状"));auto cells=grid_cells(s,value);
    if(volume(dims)!=cells.size())throw std::runtime_error("保存格子の形状とセル数が一致しません");
    packed_cells(s,s.ref(value,"セル"),cells.size());
    if(s.text(value,"境界")!="周期"&&s.text(value,"境界")!="固定")throw std::runtime_error("保存格子の境界が不正です");
    require_value(s,s.ref(value,"外側"));for(Id cell:cells)require_value(s,cell);
}
std::vector<Id> grid_value_children(const Space& s,Id value){
    if(s.at(value).center=="格子の進行"){
        std::vector<Id> values{s.ref(value,"雛形"),s.ref(value,"位置"),s.ref(value,"幅")};
        if(s.ref(value,"完了")>=0)values.push_back(s.ref(value,"完了"));return values;
    }
    if(s.at(value).center=="セル束"){
        if(s.ref(value,"値")>=0)return {s.ref(value,"値")};
        return {s.ref(value,"左"),s.ref(value,"右")};
    }
    auto values=grid_cells(s,value);values.push_back(s.ref(value,"形状"));values.push_back(s.ref(value,"外側"));return values;
}

namespace {
Id progress_value(Space& s,Id field,size_t offset,Id width,Id prefix){
    Id position=s.integer(static_cast<int64_t>(offset)),p=s.add("格子の進行");
    s.link(p,"雛形",field);s.link(p,"位置",position);s.link(p,"幅",width);
    if(prefix>=0)s.link(p,"完了",prefix);return p;
}
// Rewrite the same demanded center to its continuation. There is no chain of
// suspended parent calls retaining all previously evaluated cell graphs.
void continue_at(Space& s,Id node,Id field,Id plan,Id progress){
    s.at(node)=Node{"格子の分割実行",{}};
    s.link(node,"対象",field);s.link(node,"計画",plan);s.link(node,"進行",progress);s.text(node,"要求","有効");
}
}
void start_grid_chunks(Space& s,Id node,Id field,Id plan,Id width){
    require_field(s,field);
    if(s.at(plan).center!="計画の値"||s.at(width).center!="整数"||std::stoll(s.text(width,"値"))<=0)throw std::runtime_error("分割適用には計画と正の整数幅が必要です");
    Id progress=progress_value(s,field,0,width,-1);continue_at(s,node,field,plan,progress);
}
size_t grid_chunk_size(const Space& s,Id progress){
    Id field=s.ref(progress,"雛形");auto count=volume(shape(s,s.ref(field,"形状")));
    auto start=static_cast<size_t>(std::stoll(s.text(s.ref(progress,"位置"),"値")));
    auto width=static_cast<uint64_t>(std::stoll(s.text(s.ref(progress,"幅"),"値")));
    if(start>=count||width==0)throw std::runtime_error("格子の分割範囲が不正です");
    return static_cast<size_t>(std::min<uint64_t>(width,count-start));
}
Id expand_grid_chunk(Space& s,Id field,Id plan,Id progress){
    if(s.at(progress).center!="格子の進行"||s.ref(progress,"雛形")!=field)throw std::runtime_error("格子の進行と対象が一致しません");
    const auto dims=shape(s,s.ref(field,"形状"));const size_t count=volume(dims);
    const size_t start=static_cast<size_t>(std::stoll(s.text(s.ref(progress,"位置"),"値"))),length=grid_chunk_size(s,progress);
    const bool periodic=s.text(field,"境界")=="周期";const Id outside=s.ref(field,"外側");
    std::vector<Id> level;
    for(size_t index=start;index<start+length;++index){
        std::array<size_t,3> position{index%dims[0],(index/dims[0])%dims[1],index/(dims[0]*dims[1])};
        Id data=s.add("六腕の配置");
        for(size_t direction=0;direction<6;++direction){
            size_t axis=direction/2;bool positive=direction%2==0;auto adjacent=position;Id neighbor=outside;
            bool edge=positive?position[axis]+1==dims[axis]:position[axis]==0;
            if(!edge||periodic){
                adjacent[axis]=positive?(position[axis]+1)%dims[axis]:(position[axis]+dims[axis]-1)%dims[axis];
                neighbor=indexed_cell(s,field,adjacent[0]+dims[0]*(adjacent[1]+dims[1]*adjacent[2]),count);
            }
            s.at(data).arms[direction].faces[0].ref=neighbor;
        }
        Id local=s.add("十字の値");s.link(local,"中央",indexed_cell(s,field,index,count));s.link(local,"本体",data);
        Id call=instruction(s,"呼ぶ",{plan,local});level.push_back(instruction(s,"セルを包む",{call}));
    }
    while(level.size()>1){std::vector<Id> upper;
        for(size_t i=0;i<level.size();i+=2)upper.push_back(i+1==level.size()?level[i]:instruction(s,"セル束を結ぶ",{level[i],level[i+1]}));
        level=std::move(upper);
    }
    return level.at(0);
}
Id advance_grid_chunk(Space& s,Id node,Id bundle){
    // These input arrivals were checked before the chunk was expanded.
    const Node current=s.at(node);
    Id field=current.port("対象").vertices[0].ref,plan=current.port("計画").vertices[0].ref,progress=current.port("進行").vertices[0].ref;
    const size_t length=grid_chunk_size(s,progress);
    if(bundle_items(s,bundle,length).size()!=length)throw std::runtime_error("分割結果のセル数が違います");
    Id prefix=s.ref(progress,"完了");
    if(prefix>=0){Id joined=s.add("セル束");s.link(joined,"左",prefix);s.link(joined,"右",bundle);prefix=joined;}else prefix=bundle;
    size_t next=static_cast<size_t>(std::stoll(s.text(s.ref(progress,"位置"),"値")))+length;
    if(next==volume(shape(s,s.ref(field,"形状"))))return grid_compute(s,"格子を確定",{field,prefix});
    Id p=progress_value(s,field,next,s.ref(progress,"幅"),prefix);continue_at(s,node,field,plan,p);return -1;
}
}
