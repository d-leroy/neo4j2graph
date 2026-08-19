import logging
import os
import sys
from panoramix.json_to_tcm import TCM, Edge, TYPES, NODE_COMPOSITE_TYPES

logger = logging.getLogger(__name__)

class SNode:
    def __init__(self, name, stype):
        self.n = name
        self.t = stype

    def __repr__(self):
        return f"SN({self.name()}, {self.stype_name()})"

    def get_identifier(self): #for neo4j
        return id(self)

    def name(self):
        return self.n

    def stype(self):
        return self.t

    def stype_name(self):
        return self.t.__name__

    def set_stype(self, t):
        self.t = t

class VNode:
    def __init__(self, identifier, value):
        self.i = identifier
        self.v = value
    
    def __repr__(self):
        return f"VN({self.val()})"
    
    def corresponds_to(self, other):
        return self.get_identifier() == other.get_identifier()
    
    def get_identifier(self):
        return self.i

    def val(self):
        return self.v
    
    def cast(self, typ):
        if self.val() is None: return
        self.v = typ(self.val())

class TSM:

    def __init__(self, test_case_models = [], v_nodes = [], s_nodes = [], c_edges = [], s_edges = [], annotations = {"filenames": {}, "nonexistent_nodes": {}, "optional_nodes": {}}):
        self.v_nodes, self.s_nodes, self.c_edges, self.s_edges = v_nodes, s_nodes, c_edges, s_edges
        self.annotations = annotations
        for test_case in test_case_models:
            self.expand_tsm(test_case)
    
    ################### getters & list appends ###################

    def get_model(self):
        return self.get_value_nodes(), self.get_specification_nodes(), self.get_containment_edges(), self.get_specification_edges()

    def get_value_nodes(self):
        return self.v_nodes
    
    def add_value_node(self, new_node):
        self.v_nodes.append(new_node)
    
    def get_specification_nodes(self):
        return self.s_nodes
    
    def add_specification_node(self, new_node, v_id = None, v_parent_id = None):
        if v_parent_id is not None and v_id is not None: self.process_optional_spec(new_node, v_id, v_parent_id)
        self.s_nodes.append(new_node)

    def get_containment_edges(self):
        return self.c_edges
    
    def add_containment_edge(self, src, tgt, index = None):
        equal_edge = TCM.find_edges(self.get_containment_edges(), src, tgt)
        if equal_edge == []:    self.c_edges.append(TSM.create_edge(src, tgt, index))
        else:                   equal_edge[0].concat_index(index)
    
    def get_specification_edges(self):
        return self.s_edges
    
    def add_specification_edge(self, src, tgt):
        self.s_edges.append(TSM.create_edge(src, tgt))
    
    def get_annotations(self):
        return self.annotations
    
    def add_annotation(self, annotation_type, key, value):
        tsm_annotations = self.get_annotations()
        if annotation_type not in tsm_annotations: raise Exception('wrong key') #TODO

        if key in tsm_annotations[annotation_type]:
            for name in value:
                if name not in tsm_annotations[annotation_type][key]:
                    self.annotations[annotation_type][key].append(name)
        else:
            self.annotations[annotation_type][key] = value

    def get_containment_value_edges(self):
        return [edge for edge in self.get_containment_edges() if isinstance(edge.source(), VNode)]
    
    def get_containment_specification_edges(self):
        return [edge for edge in self.get_containment_edges() if isinstance(edge.source(), SNode)]

    def get_s_node_path(self, s_node):
        parts = [s_node.name()]
        current = s_node
        while True:
            parent_edges = [e for e in self.get_containment_specification_edges() if e.target() is current]
            if not parent_edges:
                break
            current = parent_edges[0].source()
            parts.append(current.name())
        return ".".join(reversed(parts))
    

    ############### Create node or edge #######################
    
    @staticmethod
    def create_s_node(name, stype):
        return SNode(name, stype)

    @staticmethod
    def create_v_node(ident, value):
        return VNode(ident, value)

    @staticmethod
    def create_edge(src, tgt, index = None):
        return Edge(src, tgt, index)
    

    ################ SPEC binary relation ##################
    
    def spec(self, node):
        return TCM.find_node_from_edge(self.get_specification_edges(), node, True)
    
    def spec_multi(self, *v_nodes):
        res = []
        for node in v_nodes:
            res.append(self.spec(node))
        return res
    
    def ceps(self, s_node):
        return TCM.find_parents(s_node, self.get_specification_edges())


    ################ expand Test Suite Model with TCM #####################

    def expand_tsm(self, tcm):
        self.previous_tsm_s_nodes = tuple(self.get_specification_nodes())
        self.tcm_annotations = tcm.get_annotations()
        tcm_root = TCM.search_root(tcm.get_edges())
        self.process_option_value(tcm_root, *tcm.get_model())

        root_id = tcm_root.get_identifier()
        self.add_annotation("filenames", root_id, self.tcm_annotations["filenames"][root_id])
        self.catch_missing_input(tcm)
        #print(self.get_annotations())

    def process_option_value(self, current_node, tcm_nodes, tcm_edges):
        logger.debug(
            "[process_option_value] name='%s' val=%r hash=%s",
            current_node.name(), current_node.val(), current_node.get_identifier()
        )

        v_nodes = self.get_value_nodes()
        for v_node in v_nodes:
            if v_node.get_identifier() == current_node.get_identifier():
                logger.debug("  -> VNode already in TSM (reuse)")
                return v_node

        new_v_node = TSM.create_v_node(*current_node.get_v_node_creation_info())
        self.add_value_node(new_v_node)
        logger.debug("  -> created new VNode %s", new_v_node)

        tsm_mother_v_node, tsm_mother_s_node, tsm_s_node= None, None, None
        tcm_mother_node = TCM.find_node_from_edge(tcm_edges, current_node, from_source = False)
        if tcm_mother_node   is not None: tsm_mother_v_node = TCM.find_node_from_hash(v_nodes, tcm_mother_node.get_identifier())
        if tsm_mother_v_node is not None: tsm_mother_s_node = self.spec(tsm_mother_v_node)
        if tsm_mother_s_node is not None: tsm_s_node = TCM.find_node(self.get_containment_specification_edges(), lambda edge : edge.source() == tsm_mother_s_node and edge.target().name() == current_node.name(), lambda edge : edge.target())
        
        if tsm_s_node is not None:
            logger.debug("  -> found existing spec '%s' stype=%s (from previous file)", tsm_s_node.name(), tsm_s_node.stype())
            tsm_new_v_type = type(new_v_node.val())
            if tsm_new_v_type is type(None) and tsm_s_node.stype() not in NODE_COMPOSITE_TYPES:
                raise TypeError(
                    f"Scalar-to-composite upgrade not supported: "
                    f"spec '{tsm_s_node.name()}' has type {tsm_s_node.stype().__name__}, "
                    f"but current node is composite."
                )
            self.process_type(new_v_node, tsm_s_node)
            self.add_specification_edge(new_v_node, tsm_s_node)
        else:
            if TCM.is_root(current_node, tcm_edges):
                new_s_node = TCM.search_root(self.get_containment_edges())
                if new_s_node is None:
                    new_s_node = TSM.create_s_node(*current_node.get_s_node_creation_info())
                    logger.debug("  -> created ROOT spec '%s' stype=%s", new_s_node.name(), new_s_node.stype())
                    self.add_specification_node(new_s_node)
                else:
                    logger.debug("  -> using existing ROOT spec '%s'", new_s_node.name())
            else:
                new_s_node = TSM.create_s_node(*current_node.get_s_node_creation_info())
                logger.debug("  -> created new spec '%s' stype=%s", new_s_node.name(), new_s_node.stype())
                self.add_specification_node(new_s_node, new_v_node.get_identifier(), tsm_mother_v_node.get_identifier())
                self.add_containment_edge(tsm_mother_s_node, new_s_node)

            self.add_specification_edge(new_v_node, new_s_node)

        edges_from_new_v_node = TCM.find_edges(tcm_edges, from_node=current_node)
        logger.debug("  -> %d child edge(s) to process", len(edges_from_new_v_node))
        for current_node_edge in edges_from_new_v_node:
            tsm_v_node_child = self.process_option_value(current_node_edge.target(), tcm_nodes, tcm_edges)
            self.add_containment_edge(new_v_node, tsm_v_node_child, current_node_edge.get_index())
        return new_v_node
    
    def process_type(self, tsm_v_node, tsm_s_node):
        if tsm_s_node.stype() in NODE_COMPOSITE_TYPES: return 
        tsm_new_v_type = type(tsm_v_node.val())
        tsm_s_nodetype = tsm_s_node.stype()
        if tsm_s_nodetype == tsm_new_v_type: return
        
        #check types
        if TYPES[tsm_s_nodetype] < TYPES[tsm_new_v_type]:
            tsm_s_node.set_stype(tsm_new_v_type)
            self.update_value_nodes_types(tsm_s_node)
        else:
            tsm_v_node.cast(tsm_s_nodetype)
    
    def update_value_nodes_types(self, s_node):
        # never used on s_node with type NoneType
        v_nodes = TCM.find_parents(s_node, self.get_specification_edges())
        for v_node in v_nodes:
            if v_node.val() is None: continue
            s_nodetype = s_node.stype()
            if type(v_node.val()) != s_nodetype:
                v_node.cast(s_nodetype)
    
    def process_optional_spec(self, s_node, v_id, v_parent_identifier):
        s_node_path = self.get_s_node_path(s_node)
        tcm_optional_nodes = self.tcm_annotations["nonexistent_nodes"]
        for parent_v_id, names in tcm_optional_nodes.items():
            if v_id == parent_v_id:
                self.add_annotation("nonexistent_nodes", s_node_path, tcm_optional_nodes[v_id])

        tsm_optional_nodes = self.get_annotations()["nonexistent_nodes"]
        parent_v_node = TCM.find_node(self.get_value_nodes(), lambda n: n.get_identifier() == v_parent_identifier)
        if parent_v_node is None: return
        parent_s_node = TCM.find_node_from_edge(self.get_specification_edges(), parent_v_node, True)
        parent_s_path = self.get_s_node_path(parent_s_node)
        for parent_s_id, names in tsm_optional_nodes.items():
            if parent_s_id == parent_s_path:
                for name in names:
                    if s_node.name() == name:
                        self.add_annotation("optional_nodes", s_node_path, name)
                        tsm_optional_nodes[parent_s_id].remove(name)
                        if tsm_optional_nodes[parent_s_id] == []:
                            del tsm_optional_nodes[parent_s_id]
                        return

        if parent_s_node in self.previous_tsm_s_nodes:
            self.add_annotation("optional_nodes", s_node_path,  s_node.name())
    
    def catch_missing_input(self, tcm):
        specs_of_tcm = set()
        for node in tcm.get_nodes():
            vn = TCM.find_node_from_hash(self.get_value_nodes(), node.get_identifier())
            sn = TCM.find_node_from_edge(self.get_specification_edges(), vn, from_source=True)
            specs_of_tcm.add(sn)
        for snode in self.get_specification_nodes():
            msn = TCM.find_node_from_edge(self.get_containment_specification_edges(), snode, from_source=False)
            if snode not in specs_of_tcm and msn in specs_of_tcm:
                self.add_annotation("optional_nodes", self.get_s_node_path(snode), snode.name())

    


def main():
    json_path = "arc_json"
    #jsons_to_process = ['Mahyco_0x5b67d7517e00.json', 'Mahyco_0x5be0ee5cb7b0.json'] #TODO passe pas sur les nulls parce que les nodes avec null sont exactement les mêmes
    jsons_to_process = ['Mahyco_0x5b67d7517e00.json', 'Mahyco_0x5aa3a2f6d0f0.json', 'Mahyco_0x5be0ee5cb7b0.json']
    processed_json = []
    for filename in jsons_to_process:
        file_path = os.path.join(json_path, filename)
        print(file_path)
        test = TCM(file_path)
        processed_json.append(test)
    
    test_tsm = TSM(processed_json)

if __name__ == "__main__":
    args = sys.argv
    if len(args) == 1: main()
    elif args[1] == 'test':
        import tests.test_tcm_to_tsm as test
        test.validate_tsm()
