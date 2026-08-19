from panoramix.json_to_tcm import *

def nodes_from_edges(edge_list):
    for edge in edge_list:
        yield edge.source()
        yield edge.target()

def format_types_isinstance(types):
    if not isinstance(types, tuple):
        if isinstance(types, list):
            types = tuple(types)
        else:
            types = (types,)
    return types

def test_node_types(*node_list_and_types):
    for node_list, node_types in node_list_and_types:
        types = format_types_isinstance(node_types)
        for node in node_list:
            assert isinstance(node, types)

def test_edge_types(edge_list, edge_type, additional_conditions = []):
    types = format_types_isinstance(edge_type)
    for edge in edge_list:
        assert isinstance(edge, types)
        for condition in additional_conditions:
            assert condition(edge)

def test_duplicate(*lists):
    for l in lists:
        assert len(l) == len(set(l)) # set compares nodes so it ensures no duplicate object is here

def test_unique_root(*node_list_and_edge_list):
    for node_list, edge_list in node_list_and_edge_list:
        assert len([root for root in node_list if TCM.find_parents(root, edge_list) == []]) == 1

def test_nodes_in_one_edge(*node_list_and_edge_list):
    for node_list, edge_list in node_list_and_edge_list:
        nodes_in_edges = set(node for node in nodes_from_edges(edge_list))
        assert len(node_list) == len(nodes_in_edges)
        for node in node_list:
            assert node in nodes_in_edges

def test_equal_edges(*edge_lists):
    for edge_list in edge_lists:

        for edge in edge_list:
            for other_edge in edge_list:
                if edge == other_edge: continue
                assert other_edge.source() != edge.source() or other_edge.target() != edge.target()

def test_unique_parent(*node_list_and_edge_list):
    for node_list, edge_list in node_list_and_edge_list:
        for node in node_list:
            assert len(TCM.find_parents(node, edge_list)) <= 1

def test_exact_unique_child(*node_list_and_edge_list):
    for node_list, edge_list in node_list_and_edge_list:
        for node in node_list:
            assert len(TCM.find_children(node, edge_list)) == 1