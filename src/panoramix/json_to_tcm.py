import os
import sys
import json
import hashlib
from numpy import format_float_scientific

NODE_SIMPLE_TYPES = (str, int, float, bool)
NODE_COMPOSITE_TYPES = (list, dict)
TYPES = {
    bool : 1,
    int : 2,
    float : 3,
    str : 4
}

class Node:

    def __init__(self, name, value, path = None, _hidden_type = None):
        self.n = name
        self.v = value
        self.path = path
        self.signature = None
        self._type = _hidden_type
        self.identifier = None
    
    def __repr__(self):
        return f"N({self.name()}, {self.val()}, {self._type})"
    
    def corresponds_to(self, other):
        return self.get_identifier() == other.get_identifier()
    
    def name(self):
        return self.n

    def val(self):
        return self.v
    
    def set_val(self, value):
        self.v = value
    
    def cast(self, typ):
        if self.val() is None: return
        self.set_val(typ(self.val()))
    
    def get_path(self):
        return self.path
    
    def get_signature(self):
        return self.signature
    
    def set_signature(self, sig):
        self.signature = sig
        self.set_identifier()
    
    def get_type(self):
        return (type(self.val()) if self._type is None else self._type)
    
    def get_stype(self):
        return self.get_type().__name__
    
    def set_type(self, t):
        self._type = t
    
    def get_v_node_creation_info(self):
        return self.get_identifier(), self.val()

    def get_s_node_creation_info(self):
        return self.name(), self.get_type()
    
    ############### hash function ###########################

    def hash_code(self):
        return hashlib.md5(repr((self.get_path(), self.get_signature())).encode()).hexdigest()
    
    def set_identifier(self):
        self.identifier = self.hash_code()

    def get_identifier(self):
        return self.identifier


class Edge:
    def __init__(self, source, target, index = None):
        self.src = source
        self.tgt = target
        if isinstance(index, list):     self.index = index
        elif isinstance(index, int):    self.index = [index]
        else:                           self.index = None
    
    def __repr__(self):
        return f"E({self.source()} -> {self.target()})"
    
    def corresponds_to(self, other):
        return self.source().corresponds_to(other.source()) and self.target().corresponds_to(other.target())
    
    def source(self):
        return self.src

    def target(self):
        return self.tgt
    
    def get_index(self):
        return self.index
    
    def concat_index(self, i):
        for index in i:
            if index not in self.get_index(): self.index.append(index)


class TCM:

    def __init__(self, file_path, data_key = None):
        self.file_path = file_path
        self.annotations = {"filenames": {}, "nonexistent_nodes": {}}
        self.nodes, self.edges = self.json_to_tcm(file_path, data_key)
        self.add_annotation("filenames", self.search_root(self.get_edges()).get_identifier(), file_path)
        self.process_nonexistent_nodes_annotation()


    ################# Loading data from json file #################

    def json_to_tcm(self, file, data_key):
        with open(file, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception as e:
                print(f"[ERROR] Failed to parse {file}: {e}")
        return self.nodify(data, data_key)

    @staticmethod
    def find_real_data(data, key):
        if key is None: return data
        if key in data: return data[key]
        else:
            for values in data.values():
                if isinstance(values, dict):
                    ret = TCM.find_real_data(values, key)
                    if ret: return ret


    ############ functions to transform data into Test Case Model ###########

    def nodify(self, data, data_key):
        data = TCM.find_real_data(data, data_key)
        path = data_key
        root = self.create_node("root", None, path)
        nodes = [root]
        edges = []
        sig = self.nodify_rec(data, root, nodes, edges, path)
        if sig is None: return [], []
        return nodes, edges

    @staticmethod
    def next_path(current_path, key):
        if current_path is None or current_path == "":
            return key
        return f"{current_path}.{key}"

    def nodify_rec(self, data, mother_node, nodes, edges, current_path):
        data_type, generator = TCM.create_generator(data, mother_node)
        mother_node.set_type(list if data_type == "list" else dict)

        signature_items = []
        for i, (k, v) in enumerate(generator):
            sig = self.process_node(k, v, mother_node, nodes, edges, self.next_path(current_path, k), i)
            if sig: signature_items.append(sig)
        
        if signature_items == []: return None
        signature_item = (data_type, sorted(signature_items)) if data_type == "dict" else (data_type, signature_items)
        mother_node.set_signature(signature_item)
        
        signature = (mother_node.name(), signature_item)
        return signature


    def process_node(self, k, v, mother_node, nodes, edges, current_path, list_index):
        if isinstance(v, NODE_SIMPLE_TYPES):
            casted_value = TCM.value_cast(v)
            new_node = self.create_node(k, casted_value, current_path)
            signature = (k, ("scalar", TCM.cast_for_signature(casted_value)))
            new_node.set_signature(signature[1])
        elif v is not None:
            new_node = self.create_node(k, None, current_path)
            signature = self.nodify_rec(v, new_node, nodes, edges, current_path)
            if signature is None:
                self.add_annotation("nonexistent_nodes", mother_node, k)
                return None
        else:
            self.add_annotation("nonexistent_nodes", mother_node, k)
            return None

        nodes.append(new_node)
        edges.append(self.create_edge(mother_node, new_node, list_index if mother_node.get_type() == list else None))
        
        return signature
    
    @staticmethod
    def create_generator(data, mother_node):
        if isinstance(data, dict):
            data_type = "dict"
            generator = ((k, v) for k, v in data.items())
        elif isinstance(data, list):
            data_type = "list"
            generator = ((mother_node.name(), v) for v in data)
        else:
            raise Exception(f"[ERROR] item {data} is type {type(data)}, expected list or dict")
        
        return data_type, generator

    @staticmethod
    def value_cast(obj):
        if isinstance(obj, str):
            if obj == "0": return False
            if obj == "1": return True

            try: return int(obj)
            except: pass
            try: return float(obj)
            except: pass
        return obj
    
    @staticmethod
    def cast_for_signature(obj):
        if isinstance(obj, (bool, int, float)): return format_float_scientific(obj)
        else:                                   return obj
        
    
    ###################### getters & node-edge creators ####################
    
    def get_nodes(self):
        return self.nodes

    def get_edges(self):
        return self.edges
    
    def get_model(self):
        return self.get_nodes(), self.get_edges()

    def create_node(self, label, value, path, stype=None):
        return Node(label, value, path, stype)
    
    def create_edge(self, source, target, index = None):
        # if index is not None: print(f"index = {index}, source : {source}, target : {target}")
        return Edge(source, target, index)
    
    def get_annotations(self, annotation_type = "all"):
        if annotation_type == "all":
            return self.annotations
        else:
            return self.annotations[annotation_type]
    
    def add_annotation(self, annotation_type, k, v):
        if k in self.annotations[annotation_type]:  self.annotations[annotation_type][k].append(v)
        else:                                       self.annotations[annotation_type][k] = [v]


    ################ node/edge finder #############################

    @staticmethod
    def find_node_from_hash(node_list, hash):
        condition = lambda node : node.get_identifier() == hash
        return TCM.find_node(node_list, condition, lambda x : x)

    @staticmethod
    def find_node_from_edge(edge_list, match_node, from_source):
        if from_source: functions = (lambda edge : edge.source() == match_node), (lambda edge : edge.target())
        else:           functions = (lambda edge : edge.target() == match_node), (lambda edge : edge.source())

        return TCM.find_node(edge_list, *functions)

    @staticmethod
    def find_node(object_list, condition, return_value = lambda x : x):
        for obj in object_list:
            if condition(obj): return return_value(obj)
        return None
    
    @staticmethod
    def find_parents(node, edge_list):
        return [edge.source() for edge in edge_list if edge.target() == node]
    
    @staticmethod
    def find_children(node, edge_list):
        return [edge.target() for edge in edge_list if edge.source() == node]
    
    @staticmethod
    def find_edges(edge_list, from_node = None, to_node = None):
        if from_node is not None and to_node is not None:
            node_condition = lambda edge : edge.source() == from_node and edge.target() == to_node
        elif from_node is not None :
            node_condition = lambda edge : edge.source() == from_node
        elif to_node is not None:
            node_condition = lambda edge : edge.target() == to_node
        else:
            return edge_list
        
        return [edge for edge in edge_list if node_condition(edge)]

    
    ################# Visualize Graph ######################        

    def show_tcm(self, alinea_length = 4, search_root=False):
        nodes, edges = self.get_model()
        root_node = TCM.search_root(nodes, edges) if search_root else nodes[0]
        print(self.show_tcm_rec("", root_node, 0, alinea_length))

    def show_tcm_rec(self, return_string, current_node, current_alinea, alinea_length):
        return_string += f"{current_node}\n"

        _, edges = self.get_model()
        children = [x.target() for x in edges if x.source() == current_node]
        if children == [] : return return_string

        next_alinea = current_alinea + alinea_length
        for child in children:
            return_string = self.show_tcm_rec(return_string + next_alinea*" ", child, next_alinea, alinea_length)
        
        return return_string


    ################ searching root of graph ################

    @staticmethod
    def is_root(node, edge_list):
        return [] == TCM.find_parents(node, edge_list)
    
    @staticmethod
    def search_root(edge_list, start_edge = 0):
        if edge_list == []: return None
        if start_edge >= len(edge_list):raise(f"[ERROR] searched root from {start_edge}th edge but there only are {len(edge_list)} edges")
        
        current_node = edge_list[start_edge].source()
        return TCM.search_root_rec(edge_list, current_node)

    @staticmethod
    def search_root_rec(edge_list, current_node):
        for edge in edge_list:
            if edge.target() == current_node:
                return TCM.search_root_rec(edge_list, edge.source())
        return current_node
    

    ################# Unify TCM types #########################

    def unify_types(self):
        paths = {}
        for node in self.get_nodes():
            if node.get_path() in paths:
                paths[node.get_path()].append(node)
            else:
                paths[node.get_path()] = [node]
        
        for nodes in paths.values():
            types = set(map(lambda n : n.get_type(), nodes))
            if len(types) != 1:
                if dict in types or list in types: raise Exception(f"Invalid types for nodes {nodes}, all of them must be the same type, either 'dict' or 'list'")
                best_type = type(None)
                for node in nodes:
                    if TYPES[best_type] < TYPES[node.get_type()]: best_type = node.get_type()
                
                for node in nodes:
                    node.cast(best_type)
    

    ################# process annotations ##################

    def process_nonexistent_nodes_annotation(self):
        annotations_to_add, annotations_to_del = [], []
        for ne_parent_node, ne_names in self.get_annotations("nonexistent_nodes").items():
            for ne_name in ne_names:
                annotations_to_add.append(("nonexistent_nodes", ne_parent_node.get_identifier(), ne_name))
            annotations_to_del.append(ne_parent_node)
        for annotation in annotations_to_add:
            self.add_annotation(*annotation)
        for annotation in annotations_to_del:
            del self.get_annotations("nonexistent_nodes")[annotation]
        


def main():
    json_path = "arc_json"
    processed_json = []
    max_process = 2
    for filename in os.listdir(json_path):
        if filename.endswith(".json"):
            file_path = os.path.join(json_path, filename)
            print(file_path)
            test = TCM(file_path)
            processed_json.append(test)
            if len(processed_json) >= max_process:
                break

    max_show = 2
    for tcm in processed_json[:max_show]:
        tcm.show_tcm()
        print(tcm.get_annotations())
            



if __name__ == "__main__":
    args = sys.argv
    if len(args) == 1: main()
    elif args[1] == 'test':
        import tests.test_json_to_tcm as test
        test.validate_tcm()
