#include "cross.hpp"
#include <algorithm>

namespace cross {
size_t compact_space(Space& s) {
    s.validate();
    if(s.at(s.root).center!="計算空間")throw std::runtime_error("回収する計算空間ではありません");
    const size_t before=s.nodes.size();
    // A completed computation is observationally its immutable result. Guest
    // programs cannot inspect executable node IDs or the diagnostic history.
    std::vector<Id> redirect(before);
    for(size_t i=0;i<before;++i) {
        const Node& n=s.nodes[i];Id done=n.port("結果").vertices[0].ref;
        redirect[i]=!is_value(n.center)&&done>=0?done:static_cast<Id>(i);
    }
    Node root=s.at(s.root);
    int history=root.find("履歴");if(history>=0)root.arms[history]=Arm{};
    std::vector<unsigned char> marked(before);
    std::vector<Id> pending{s.root};
    while(!pending.empty()) {
        Id id=redirect[pending.back()];pending.pop_back();if(marked[id])continue;marked[id]=1;
        const auto& n=id==s.root?root:s.at(id);
        for(const auto& arm:n.arms)for(const auto* sites:{&arm.faces,&arm.edges,&arm.vertices})
            for(const auto& site:*sites)if(site.ref>=0)pending.push_back(site.ref);
    }
    Space collected;collected.limit=s.limit;
    std::vector<Id> relocated(before,-1);
    for(size_t i=0;i<before;++i)if(marked[i]) {
        relocated[i]=static_cast<Id>(collected.nodes.size());
        collected.nodes.push_back(static_cast<Id>(i)==s.root?root:s.nodes[i]);
    }
    collected.root=relocated[s.root];
    for(auto& node:collected.nodes)for(auto& arm:node.arms)for(auto* sites:{&arm.faces,&arm.edges,&arm.vertices})
        for(auto& site:*sites)if(site.ref>=0)site.ref=relocated[redirect[site.ref]];
    collected.validate();
    s=std::move(collected);
    return before-s.nodes.size();
}

Report run_program(Space& s,const std::string& policy,size_t maximum,uint64_t seed,
                   const std::string& scheduler,const std::string& memory,size_t slice) {
    if(memory!="full"&&memory!="compact")throw std::runtime_error("未知のメモリ保持方式です");
    if(memory=="full") {
        auto report=Machine(s).run(policy,maximum,seed,scheduler);
        return report;
    }
    if(slice==0)throw std::runtime_error("回収間隔は正の段階数です");
    Report total;total.scheduler=scheduler;total.memory_policy=memory;total.status="STEP_BUDGET";
    total.peak_nodes=s.nodes.size();
    // Queues are rebuilt after relocation; all resumable state remains in Node.
    // This is a host mark/compact collector, not constant-time local hardware.
    do {
        const size_t allowance=std::min(slice,maximum-total.steps);
        auto part=Machine(s).run(policy,allowance,seed+total.collections,scheduler);
        total.steps+=part.steps;total.transitions+=part.transitions;
        total.grid_expansions+=part.grid_expansions;total.expanded_cells+=part.expanded_cells;total.neighbor_slots+=part.neighbor_slots;
        total.grid_chunks+=part.grid_chunks;total.max_chunk_cells=std::max(total.max_chunk_cells,part.max_chunk_cells);
        total.max_enabled=std::max(total.max_enabled,part.max_enabled);
        total.node_inspections+=part.node_inspections;total.index_nodes+=part.index_nodes;
        total.peak_nodes=std::max(total.peak_nodes,part.peak_nodes);
        total.status=part.status;
        size_t reclaimed=compact_space(s);total.reclaimed_nodes+=reclaimed;++total.collections;
        total.value=result(s,s.ref(s.root,"実行"));
        if(part.status!="STEP_BUDGET"&&part.status!="NODE_BUDGET")break;
        if(part.status=="NODE_BUDGET"&&reclaimed==0)break;
        if(total.steps==maximum){total.status="STEP_BUDGET";break;}
    }while(total.steps<maximum);
    return total;
}
}
