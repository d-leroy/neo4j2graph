from panoramix.tcm_to_tsm import *
from tests.test_graphs import *
from itertools import combinations

def test_structure(tsm):
    vn, sn, ce, se = tsm.get_model()
    test_node_types((vn, VNode), (sn, SNode))
    test_edge_types(ce, Edge, [lambda edge: isinstance(edge.source(), (VNode, SNode)), lambda edge: type(edge.source()) == type(edge.target())])
    test_edge_types(se, Edge, [lambda edge: isinstance(edge.source(), (VNode)) and isinstance(edge.target(), SNode)])

def test_validity(tsm):
    vn, sn, ce, se = tsm.get_model()

    test_duplicate(vn, sn, ce, se) # no duplicates in lists
    test_unique_root((sn, ce)) #only one root for specification side
    test_nodes_in_one_edge((vn+sn, ce), (vn+sn, se)) # node is in at least 1 edge and all nodes from edges are in the node list
    test_equal_edges(ce, se)# 2 edges cannot have the same source and target at the same time
    # an edge source is not a leaf
    for edge in ce:
        if isinstance(edge.source(), VNode):assert edge.source().val() is None
        else:                               assert edge.source().stype() in NODE_COMPOSITE_TYPES
    test_unique_parent((sn, ce)) # a node has at most 1 parent for specification ones
    test_exact_unique_child((vn, se)) # a value node is specified by only one spec node
    test_vn_sn_type_verification(se) # all value nodes have their values of the type notified in their spec node
    test_vn_child_spec_is_vn_spec_child(tsm) # proposition 5 of research paper : if vn contains vn', spec(vn) contains spec(vn')
    test_acyclic_extended(tsm) # acyclic graph
    
def test_acyclic_extended(tsm):
    vn, sn, ce, se = tsm.get_model()

    # edge does not have the same source and target
    for edge in ce:
        assert edge.source() != edge.target()
    
    # for spec nodes
    # we know that :    there is exactly 1 root
    #                   each node only has 1 parent
    # so we just need to test for rings / if we follow the path from the root, 
    # we must catch all nodes and not find a seen_node
    spec_containment_edges = tsm.get_containment_specification_edges()
    root = TCM.search_root(spec_containment_edges, start_edge = len(spec_containment_edges)//2)
    seen_nodes = [root]
    test_acyclic_rec(root, spec_containment_edges, seen_nodes)
    assert len(seen_nodes) == len(sn)

    # for value nodes
    # we know nothing, so for each root, we must show that a node from depth n doesn't have an edge going to depth m < n
    # in reality here, depth m = depth n + 1
    # and that each vn node is found by traversing each root
    val_containment_edges = tsm.get_containment_value_edges()
    roots = [root for root in vn if TCM.find_parents(root, val_containment_edges) == []]
    verified_nodes = {} # node to depth
    for root in roots:
        depth_counter = 0
        test_acyclic_extended_rec(root, val_containment_edges, verified_nodes, depth_counter)
    assert len(verified_nodes) == len(vn)


def test_acyclic_rec(node, edges, seen_nodes):
    node_children = TCM.find_children(node, edges)
    for child in node_children:
        assert child not in seen_nodes
        seen_nodes.append(child)
        test_acyclic_rec(child, edges, seen_nodes)

def test_acyclic_extended_rec(node, edges, verified_nodes, depth_counter):
    if node in verified_nodes:
        assert verified_nodes[node] >= depth_counter # in reality verified_nodes[node] == depth_counter
        return
    node_children = TCM.find_children(node, edges)
    for child in node_children:
        test_acyclic_extended_rec(child, edges, verified_nodes, depth_counter+1)
    verified_nodes[node] = depth_counter

def test_vn_sn_type_verification(spec_edges):
    for edge in spec_edges:
        assert (edge.source().val() == None and edge.target().stype() in NODE_COMPOSITE_TYPES) or isinstance(edge.source().val(), edge.target().stype())

def test_vn_child_spec_is_vn_spec_child(tsm):
    vce, sce = tsm.get_containment_value_edges(), tsm.get_containment_specification_edges()
    for edge in vce:
        assert len(TCM.find_edges(sce, tsm.spec(edge.source()), tsm.spec(edge.target()))) == 1

def test_TSM_contains_TCMs(tsm, tcms):
    vn, cve = tsm.get_value_nodes(), tsm.get_containment_value_edges()
    for tcm in tcms:
        nodes, edges = tcm.get_model()
        for node in nodes:
            exists = False
            for v_node in vn:
                if v_node.corresponds_to(node):
                    exists = True
                    break
            assert exists
        for edge in edges:
            exists = False
            for v_edge in cve:
                if v_edge.corresponds_to(edge):
                    exists = True
                    break
            assert exists


def test_tsm(tsm):
    test_structure(tsm)
    test_validity(tsm)

def validate_tsm():
    json_path = "arc_json/arc_json_tests"
    processed_json = []
    for filename in os.listdir(json_path):
        if filename.endswith(".json"):
            file_path = os.path.join(json_path, filename)
            processed_json.append(TCM(file_path, 'mahyco'))
    tcm_combinations = list(combinations(processed_json, len(processed_json)-1))
    for comb in tcm_combinations:
        tsm = TSM(list(comb))
        test_tsm(tsm)
        test_TSM_contains_TCMs(tsm, list(comb))

    tsm = TSM(processed_json)
    test_tsm(tsm)
    test_TSM_contains_TCMs(tsm, processed_json)
    print("ALL tests validated")
    