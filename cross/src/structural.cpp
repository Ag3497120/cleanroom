#include "cross.hpp"
#include <algorithm>
#include <array>

namespace cross {
namespace {
using Vector = std::array<int, 3>;
const std::array<Vector, 6> directions{{{1,0,0},{-1,0,0},{0,1,0},{0,-1,0},{0,0,1},{0,0,-1}}};
const std::array<std::string, 6> direction_names{{"+x","-x","+y","-y","+z","-z"}};
const std::array<std::string, 4> face_names{{"北","南","東","西"}};
const std::array<std::string, 4> edge_names{{"北東","南東","南西","北西"}};
const std::array<std::string, 4> vertex_names{{"北東端","南東端","南西端","北西端"}};
const std::array<std::string, 3> site_names{{"面","辺","頂点"}};
const std::array<Vector, 4> face_offsets{{{0,1,0},{0,-1,0},{1,0,0},{-1,0,0}}};
const std::array<Vector, 4> corner_offsets{{{1,1,0},{1,-1,0},{-1,-1,0},{-1,1,0}}};
Vector cross_product(Vector a, Vector b) {
    return {a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]};
}
int dot(Vector a, Vector b) { return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]; }
Vector rotate(Vector value, Vector axis) {
    auto result=cross_product(axis,value);
    for(int i=0;i<3;++i) result[i]+=axis[i]*dot(axis,value);
    return result;
}
std::pair<Vector,Vector> basis(Vector outward) {
    Vector reference=outward[2]==0?Vector{0,0,1}:Vector{0,1,0};
    Vector east=cross_product(reference,outward);
    return {east,cross_product(outward,east)};
}
template<size_t N> int index(const std::array<std::string,N>& names,const std::string& name) {
    auto it=std::find(names.begin(),names.end(),name);
    if(it==names.end()) throw std::runtime_error("未知の構造上の場所: "+name);
    return static_cast<int>(it-names.begin());
}
struct Address {int arm,kind,site;};
Address address(const std::string& text) {
    auto first=text.find('/'),second=first==std::string::npos?first:text.find('/',first+1);
    if(second==std::string::npos||text.find('/',second+1)!=std::string::npos)
        throw std::runtime_error("場所は +x/面/北 のように指定してください");
    int arm=index(direction_names,text.substr(0,first));
    int kind=index(site_names,text.substr(first+1,second-first-1));
    auto site=text.substr(second+1);
    return {arm,kind,kind==0?index(face_names,site):kind==1?index(edge_names,site):index(vertex_names,site)};
}
Site& slot(Node& n,Address a) {
    auto& arm=n.arms[a.arm];
    return a.kind==0?arm.faces[a.site]:a.kind==1?arm.edges[a.site]:arm.vertices[a.site];
}
std::string text_value(const Space& s,Id id) {
    if(s.at(id).center!="文章")throw std::runtime_error("場所・軸・項目名には文章が必要です");
    return s.text(id,"値");
}
Id body(const Space& s,Id value) {
    if(s.at(value).center!="十字の値")throw std::runtime_error("十字の値が必要です");
    return s.ref(value,"本体");
}
Id wrap(Space& s,Id center,Id data) {
    Id value=s.add("十字の値");s.link(value,"中央",center);s.link(value,"本体",data);return value;
}
Id copy_body(Space& s,Id source) {
    Node copy=s.at(source);Id fresh=s.add("六腕の配置");s.at(fresh)=std::move(copy);return fresh;
}
std::vector<Id> entries(const Space& s,Id record) {
    if(s.at(record).center!="記録")throw std::runtime_error("記録の値が必要です");
    return s.items(s.ref(record,"内容"));
}
}

std::vector<std::string> structural_roles(const std::string& op) {
    if(op=="十字を作る")return {"中央"};
    if(op=="中央を読む")return {"対象"};
    if(op=="中央に置く")return {"対象","値"};
    if(op=="場所を読む"||op=="場所を持つ")return {"対象","場所"};
    if(op=="場所に置く")return {"対象","場所","値"};
    if(op=="十字を回す")return {"対象","軸","回数"};
    if(op=="項目を読む"||op=="項目を持つ")return {"対象","名前"};
    if(op=="項目に置く")return {"対象","名前","値"};
    return {};
}

Id structural_compute(Space& s,const std::string& op,const std::vector<Id>& values) {
    if(op=="十字を作る")return wrap(s,values[0],s.add("六腕の配置"));
    if(op=="項目を読む"||op=="項目を持つ"||op=="項目に置く") {
        auto contents=entries(s,values[0]);auto name=text_value(s,values[1]);
        auto it=std::find_if(contents.begin(),contents.end(),[&](Id e){return s.text(s.ref(e,"名前"),"値")==name;});
        if(op=="項目を持つ")return s.boolean(it!=contents.end());
        if(op=="項目を読む") {
            if(it==contents.end())throw std::runtime_error("記録に項目がありません: "+name);
            return s.ref(*it,"値");
        }
        Id item=s.add("項目");s.link(item,"名前",values[1]);s.link(item,"値",values[2]);
        if(it==contents.end())contents.push_back(item);else *it=item;
        Id bundle=s.sequence(contents),updated=s.add("記録");s.link(updated,"内容",bundle);return updated;
    }
    Id original=body(s,values[0]);
    if(op=="中央を読む")return s.ref(values[0],"中央");
    if(op=="中央に置く")return wrap(s,values[1],original);
    if(op=="場所を読む"||op=="場所を持つ"||op=="場所に置く") {
        auto where=address(text_value(s,values[1]));
        // A copied Node avoids dangling references when allocating in Space.
        Node data=s.at(original);Id found=slot(data,where).ref;
        if(op=="場所を持つ")return s.boolean(found>=0);
        if(op=="場所を読む") {
            if(found<0)throw std::runtime_error("指定場所には値がありません");
            return found;
        }
        Id fresh=copy_body(s,original);slot(s.at(fresh),where).ref=values[2];
        return wrap(s,s.ref(values[0],"中央"),fresh);
    }
    if(op=="十字を回す") {
        int axis=index(direction_names,text_value(s,values[1]));
        if(s.at(values[2]).center!="整数")throw std::runtime_error("回転回数には整数が必要です");
        int turns=static_cast<int>(std::stoll(s.text(values[2],"値"))%4);
        if(turns<0)turns+=4;
        Node data=s.at(original);
        for(int turn=0;turn<turns;++turn) {
            Node next{"六腕の配置",{}};
            for(int arm=0;arm<6;++arm) {
                Vector w=directions[arm],rotated=rotate(w,directions[axis]);
                int destination=static_cast<int>(std::find(directions.begin(),directions.end(),rotated)-directions.begin());
                auto [u,v]=basis(w);auto [new_u,new_v]=basis(rotated);
                for(int kind=0;kind<3;++kind)for(int site=0;site<4;++site) {
                    const auto& offsets=kind==0?face_offsets:corner_offsets;
                    Vector offset{};
                    for(int k=0;k<3;++k)offset[k]=offsets[site][0]*u[k]+offsets[site][1]*v[k];
                    offset=rotate(offset,directions[axis]);
                    Vector local{dot(offset,new_u),dot(offset,new_v),0};
                    int next_site=static_cast<int>(std::find(offsets.begin(),offsets.end(),local)-offsets.begin());
                    if(next_site==4||destination==6)throw std::runtime_error("回転の直交性が壊れています");
                    slot(next,{destination,kind,next_site})=slot(data,{arm,kind,site});
                }
            }
            data=std::move(next);
        }
        Id rotated=s.add("六腕の配置");s.at(rotated)=std::move(data);
        return wrap(s,s.ref(values[0],"中央"),rotated);
    }
    throw std::runtime_error("未定義の構造演算です");
}

void validate_structural_value(const Space& s,Id value) {
    if(!is_value(s.at(s.ref(value,"中央")).center))throw std::runtime_error("十字の中央が値ではありません");
    const auto& data=s.at(body(s,value));
    if(data.center!="六腕の配置")throw std::runtime_error("十字の配置本体が不正です");
    for(const auto& arm:data.arms)for(const auto* sites:{&arm.faces,&arm.edges,&arm.vertices})for(const auto& site:*sites) {
        if(!site.text.empty()||(site.ref>=0&&!is_value(s.at(site.ref).center)))
            throw std::runtime_error("十字の場所には値への参照だけを格納します");
    }
}

std::vector<std::pair<std::string,Id>> structural_entries(const Space& s,Id value) {
    Node data=s.at(body(s,value));
    std::vector<std::pair<std::string,Id>> entries;
    for(int arm=0;arm<6;++arm)for(int kind=0;kind<3;++kind)for(int site=0;site<4;++site) {
        Id ref=slot(data,{arm,kind,site}).ref;
        if(ref>=0)entries.emplace_back(direction_names[arm]+"/"+site_names[kind]+"/"+
            (kind==0?face_names[site]:kind==1?edge_names[site]:vertex_names[site]),ref);
    }
    return entries;
}

void validate_utf8(const std::string& text) {
    for(size_t i=0;i<text.size();) {
        unsigned char first=text[i++];
        if(first<0x80)continue;
        int count=first>=0xc2&&first<=0xdf?1:first>=0xe0&&first<=0xef?2:first>=0xf0&&first<=0xf4?3:-1;
        if(count<0||i+static_cast<size_t>(count)>text.size())throw std::runtime_error("不正なUTF-8です");
        unsigned value=first&((1u<<(6-count))-1u);
        for(int n=0;n<count;++n){unsigned char next=text[i++];if((next&0xc0)!=0x80)throw std::runtime_error("不正なUTF-8です");value=(value<<6)|(next&0x3f);}
        if((count==1&&value<0x80)||(count==2&&value<0x800)||(count==3&&value<0x10000)||value>0x10ffff||(value>=0xd800&&value<=0xdfff))
            throw std::runtime_error("不正なUnicode符号位置です");
    }
}
}
