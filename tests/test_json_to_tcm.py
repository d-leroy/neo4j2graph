from panoramix.json_to_tcm import *
from tests.test_graphs import *

#################### TESTS ######################""

def test_node(node):
    assert node.val() != node._type # don't want them both to be None

def test_structure(tcm):
    nodes, edges = tcm.get_model()

    test_node_types((nodes, Node))
    for obj in nodes:
        test_node(obj)
    
    test_edge_types(edges, Edge, [lambda edge: isinstance(edge.source(), Node) and isinstance(edge.target(), Node)])

def test_validity(tcm):
    nodes, edges = tcm.get_model()

    test_duplicate(nodes, edges) # no duplicate node
    test_unique_root((nodes, edges)) # only one root
    test_nodes_in_one_edge((nodes, edges)) # node is in at least 1 edge and all nodes from edges are in the node list
    # a node must have a value type in those 2 sets
    for node in nodes:
        assert isinstance(node.val(), NODE_SIMPLE_TYPES) or node.get_type() in NODE_COMPOSITE_TYPES
    # an edge source is not a leaf
    for edge in edges:
        assert edge.source().val() is None and edge.source().get_type() in NODE_COMPOSITE_TYPES
    # 2 edges cannot have the same source and target at the same time
    test_equal_edges(edges)
    # a node has at most 1 parent
    test_unique_parent((nodes, edges))
    # a map node has all its children with distinct names
    # a list node has all its children with identical names to it
    for node in nodes:
        if node.get_type() in NODE_COMPOSITE_TYPES:
            children = tcm.find_children(node, edges)
            assert len(children) != 0
            children_names = set(map(lambda child: child.name(), children))
            if node.get_type() == list:
                assert len(children_names) == 1 and node.name() in children_names
            elif node.get_type() == dict:
                assert len(children) == len(children_names)
    
    test_acyclic(tcm)


def test_acyclic(tcm):
    nodes = tcm.get_nodes()
    edges = tcm.get_edges()

    # edge does not have the same source and target
    for edge in edges:
        assert edge.source() != edge.target()
    
    # we know that :    there is exactly 1 root
    #                   each node only has 1 parent
    # so we just need to test for rings / if we follow the path from the root, 
    # we must catch all nodes and not find a seen_node
    root = tcm.search_root(edges, start_edge = len(edges)//2)
    seen_nodes = [root]
    test_acyclic_rec(root, edges, seen_nodes)
    assert len(seen_nodes) == len(nodes)

def test_acyclic_rec(node, edges, seen_nodes):
    node_children = TCM.find_children(node, edges)
    for child in node_children:
        assert child not in seen_nodes
        seen_nodes.append(child)
        test_acyclic_rec(child, edges, seen_nodes)

def test_tcm(tcm):
    test_structure(tcm)
    test_validity(tcm)
        
def validate_tcm():
    json_path = "arc_json/arc_json_tests"
    for filename in os.listdir(json_path):
        if filename.endswith(".json"):
            file_path = os.path.join(json_path, filename)
            print(file_path)
            tcm = TCM(file_path)
            test_tcm(tcm)
    print("ALL tests have been validated")
    
