#pragma once
#include <array>
#include <cstdint>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>
#include <stdexcept>

namespace cross {
using Id = int;
struct Site { std::string text; Id ref = -1; };
struct Arm {
    std::array<Site, 4> faces, edges, vertices;
};
struct Node {
    std::string center;
    std::array<Arm, 6> arms;
    int find(const std::string& role) const;
    Arm& port(const std::string& role);
    const Arm& port(const std::string& role) const;
};
struct Space {
    std::vector<Node> nodes;
    Id root = -1;
    size_t limit = 100000;
    Id add(const std::string& center);
    Node& at(Id id);
    const Node& at(Id id) const;
    void link(Id node, const std::string& role, Id target);
    Id ref(Id node, const std::string& role) const;
    void text(Id node, const std::string& role, const std::string& value);
    std::string text(Id node, const std::string& role) const;
    Id integer(int64_t n);
    Id boolean(bool b);
    Id string(const std::string& text);
    Id error(const std::string& text);
    Id sequence(const std::vector<Id>& items);
    std::vector<Id> items(Id root) const;
    void validate() const;
    void save(const std::string& path) const;
    static Space load(const std::string& path, size_t limit = 100000);
};
struct BudgetError : std::runtime_error { using std::runtime_error::runtime_error; };
std::string read_file(const std::string& path, size_t max_bytes = 64 * 1024 * 1024);
std::string quote_json(const std::string& text);
Id import_json(Space& space, const std::string& text);
std::string export_json(const Space& space, Id value);
bool is_value(const std::string& center);
Id result(const Space& space, Id node);
std::vector<std::string> roles(const std::string& op);
std::string operation(const Space& space, const std::string& center);
Id instantiate(Space& space, Id body, const std::map<Id, Id>& substitutions);
Space compile(const std::string& source, const std::string& input = "null", size_t limit = 100000);
struct Transition {
    Id node = -1;
    std::string rule;
    int port = -1;
    std::vector<Id> inputs;
    std::vector<Id> requests;
};
struct Report {
    std::string status;
    Id value = -1;
    size_t steps = 0, max_enabled = 0, transitions = 0;
    std::string scheduler = "events";
    size_t node_inspections = 0, index_nodes = 0;
    std::string memory_policy = "full";
    size_t collections = 0, reclaimed_nodes = 0, peak_nodes = 0;
    size_t grid_expansions = 0, expanded_cells = 0, neighbor_slots = 0;
    size_t grid_chunks = 0, max_chunk_cells = 0;
};
class Machine {
    Space& s;
    std::map<std::string, std::string> aliases;
    std::string resolve(const std::string& center) const;
    std::optional<Transition> enabled_at(Id node) const;
    bool need(Id node, Id dependency, Transition& t) const;
    Id compute(const std::string& op, const std::vector<Id>& values);
    Id apply(const Transition& t);
public:
    explicit Machine(Space& space);
    Id output() const;
    void request(Id node);
    std::vector<Transition> enabled() const;
    Report run(const std::string& policy = "batch", size_t steps = 10000, uint64_t seed = 1,
               const std::string& scheduler = "events");
};
std::string report_json(const Space& space, const Report& report);
// First-class geometric values. The runtime keeps these in the same Node store.
std::vector<std::string> structural_roles(const std::string& op);
Id structural_compute(Space& space, const std::string& op, const std::vector<Id>& values);
void validate_structural_value(const Space& space, Id value);
std::vector<std::pair<std::string, Id>> structural_entries(const Space& space, Id value);
void validate_utf8(const std::string& text);
// Immutable rectangular fields and user-defined synchronous neighborhood maps.
std::vector<std::string> grid_roles(const std::string& op);
Id grid_compute(Space& space, const std::string& op, const std::vector<Id>& values);
Id expand_grid(Space& space, Id field, Id plan);
void validate_grid_value(const Space& space, Id value);
std::vector<Id> grid_value_children(const Space& space, Id value);
std::vector<Id> grid_cells(const Space& space, Id value);
void start_grid_chunks(Space& space, Id node, Id field, Id plan, Id width);
Id expand_grid_chunk(Space& space, Id field, Id plan, Id progress);
Id advance_grid_chunk(Space& space, Id node, Id bundle);
size_t grid_chunk_size(const Space& space, Id progress);
size_t compact_space(Space& space);
Report run_program(Space& space, const std::string& policy = "batch", size_t steps = 10000,
                   uint64_t seed = 1, const std::string& scheduler = "events",
                   const std::string& memory = "full", size_t slice = 256);
}
