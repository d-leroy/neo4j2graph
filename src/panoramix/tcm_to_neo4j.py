from panoramix.json_to_tcm import TCM, TYPES, Node, Edge
from panoramix.tsm_to_neo4j import sanitize, TSM_creation_query, STARTING_CHAR
from panoramix.tcm_to_tsm import TSM
from neo4j import GraphDatabase
import os, sys
from functools import reduce
from pydoc import locate

class TCMtoDB:
    @staticmethod
    def setup_variables(tcm:TCM):
        tcm.unify_types() # needed for type consistency
        TCMtoDB.final_queries = {"node_matching" : {}, "node_creation" : [], "edge_creation" : [], "type_change" : {}}
        TCMtoDB.db_info = {"db_value_nodes" : {}, "db_specification_nodes" : {}, "db_spec_paths" : {}, 
                           "db_optional_nodes" : {}, "db_annotation_optional_node_id" : None}
        TCMtoDB.nodes_created = []
        TCMtoDB.path_of_s_nodes_to_create = []
        TCMtoDB.tcm_annotations = tcm.get_annotations()


    ################## Expanding db with a tcm ######################
    
    @staticmethod
    def expand_neo4j_tsm(driver, db: str, tcm: TCM)->None:
        TCMtoDB.setup_variables(tcm)

        with driver.session(database = db) as session:
            TCMtoDB.get_db_nodes_start(session, tcm)
        root = tcm.search_root(tcm.get_edges())
        
        if root.get_identifier() in TCMtoDB.db_info["db_value_nodes"]:
            with driver.session(database = db) as session:
                session.run(TCMtoDB.annotation_tcm_in_db_query(root.get_identifier()))
            return

        TCMtoDB.process_option_value_to_neo4j(None, root, tcm.get_edges())
        TCMtoDB.catch_missing_input(tcm)
        with driver.session(database = db) as session:
            TCMtoDB.process_final_queries(session)

    @staticmethod
    def process_option_value_to_neo4j(mother_specification_element: str|list|None, current_node: Node, tcm_edges: list[Edge])->None:
        if current_node.get_identifier() in TCMtoDB.db_info["db_value_nodes"]: return
        if current_node.get_identifier() in TCMtoDB.nodes_created: return
        print(f"Node to add to the graph : {current_node}")

        db_sn_element = None
        if TCMtoDB.is_from_db(mother_specification_element):
            db_sn_element = TCMtoDB.find_s_option(mother_specification_element, current_node)

        if db_sn_element is not None:
            new_msn_element = db_sn_element.element_id
            TCMtoDB.process_type_db(current_node, db_sn_element)
        else: # no need to process type here because the TCM has been unified in the init so each equivalent tcm node has the same type
            if mother_specification_element is None: new_msn_element = TCMtoDB.process_root(current_node) #node is root
            else:                                    new_msn_element = TCMtoDB.process_node(current_node, mother_specification_element)
        
        TCMtoDB.node_creation(*current_node.get_v_node_creation_info())
        TCMtoDB.edge_creation([STARTING_CHAR+current_node.get_identifier()], new_msn_element, "IS_SPECIFIED_BY")
        TCMtoDB.process_nonexistent_child_nodes(current_node, new_msn_element)
        
        edges_from_current_node = TCM.find_edges(tcm_edges, from_node=current_node)
        for edge_to_child in edges_from_current_node:
            child_id = edge_to_child.target().get_identifier()
            if child_id in TCMtoDB.db_info["db_value_nodes"]: child_ref_id = TCMtoDB.db_info["db_value_nodes"][child_id]
            else:
                TCMtoDB.process_option_value_to_neo4j(new_msn_element, edge_to_child.target(), tcm_edges)
                child_ref_id = [STARTING_CHAR+child_id]
            TCMtoDB.edge_creation([STARTING_CHAR+current_node.get_identifier()], child_ref_id, "CONTAINS", edge_to_child.get_index())


    @staticmethod
    def process_root(current_node: Node)->list[str]:
        if TCMtoDB.db_info["db_specification_nodes"] != {}:
            return TCMtoDB.get_db_s_root().element_id
        else:
            identifier = "s" + current_node.get_identifier()
            TCMtoDB.path_of_s_nodes_to_create.append((current_node.get_path(), identifier))
            TCMtoDB.node_creation(identifier, current_node.name(), current_node.get_stype())
            return [identifier]

    @staticmethod
    def process_node(current_node: Node, mother_specification_element: str|list)->list[str]:
        mother_info = TCM.find_node(TCMtoDB.path_of_s_nodes_to_create, lambda n : n[0] == current_node.get_path(), lambda n : n[1])
        if mother_info is not None: identifier = mother_info
        else:
            identifier = "s" + current_node.get_identifier()
            TCMtoDB.path_of_s_nodes_to_create.append((current_node.get_path(), identifier))
            TCMtoDB.node_creation(identifier, current_node.name(), current_node.get_stype())
            TCMtoDB.edge_creation(mother_specification_element, [identifier], "CONTAINS")
            if isinstance(mother_specification_element, str): # mother spec in db but we have to create a child, therefore the child is optional
                TCMtoDB.edge_creation(TCMtoDB.db_info["db_annotation_optional_node_id"], [identifier], "ANNOTATES")

        return [identifier]
    
    @staticmethod
    def process_nonexistent_child_nodes(current_node: Node, mother_node):
        if current_node.get_identifier() in TCMtoDB.tcm_annotations["nonexistent_nodes"]:
            node_names = TCMtoDB.tcm_annotations["nonexistent_nodes"][current_node.get_identifier()]
            if current_node.get_path() not in TCMtoDB.db_info["db_optional_nodes"]:
                for node_name in node_names:
                    TCMtoDB.create_nonexistent_node(current_node, mother_node, node_name)
            else:
                for node_name in node_names:
                    if node_name not in TCMtoDB.db_info["db_optional_nodes"][current_node.get_path()]:
                        TCMtoDB.create_nonexistent_node(current_node, mother_node, node_name)
                        
    @staticmethod
    def create_nonexistent_node(current_node: Node, mother_node, node_name: str):
        identifier = "s" + current_node.get_identifier()
        identifier = "s" + str(id(identifier))+identifier
        TCMtoDB.node_creation(identifier, node_name, 'bool')
        TCMtoDB.edge_creation(mother_node, [identifier], "CONTAINS")
        TCMtoDB.edge_creation(TCMtoDB.db_info["db_annotation_optional_node_id"], [identifier], "ANNOTATES")
    
    @staticmethod
    def catch_missing_input(tcm):
        specs_path_of_db = TCMtoDB.db_info["db_spec_paths"]
        specs_path_of_tcm = set(map(lambda x: x.get_path(), tcm.get_nodes()))
        for snode_path in specs_path_of_db:
            snode_id, msn_path = specs_path_of_db[snode_path]
            if snode_path not in specs_path_of_tcm and msn_path in specs_path_of_tcm:
                TCMtoDB.edge_creation(TCMtoDB.db_info["db_annotation_optional_node_id"], snode_id, "ANNOTATES")
    

    ################### get db infos ######################

    @staticmethod
    def get_db_nodes_start(session, tcm:TCM)->None:
        TCMtoDB.db_info["db_specification_nodes"] = TCMtoDB.get_db_specification_nodes(session)
        TCMtoDB.db_info["db_spec_paths"] = TCMtoDB.get_db_spec_nodes_paths(session)
        TCMtoDB.db_info["db_value_nodes"] = TCMtoDB.already_existing_value_nodes(session, tcm)
        TCMtoDB.db_info["db_annotation_optional_node_id"], TCMtoDB.db_info["db_optional_nodes"] = TCMtoDB.get_db_optional_annotation_node(session)

    @staticmethod
    def already_existing_value_nodes(session, tcm:TCM)-> dict[str, str]:
        identifiers = list(set(map(lambda x: x.get_identifier(), tcm.get_nodes())))
        query = f"""WITH [{str(identifiers)[1:-1]}] AS identifiers UNWIND identifiers AS ident
OPTIONAL MATCH (v:ValueNode {{identifier: ident}})
RETURN ident, elementId(v) AS e_id"""
        query_results = session.run(query)
        return {ident: element_id for ident, element_id in query_results if element_id is not None}

    @staticmethod
    def get_db_specification_nodes(session)->dict:
        query = """MATCH (s:SpecificationNode)
OPTIONAL MATCH (s)-[:CONTAINS]->(a)
RETURN s, collect(elementId(a))"""
        results = session.run(query)
        return {node: list(map(lambda s: s[39:], child_list)) for node, child_list in results}

    @staticmethod
    def get_db_optional_annotation_node(session):
        query = "OPTIONAL MATCH (a:AnnotationNode {annotation: 'This value is optional'}) RETURN elementId(a)"
        result = session.run(query).single()[0]
        if result is None:
            if TCMtoDB.tcm_annotations["nonexistent_nodes"] == {}:
                return None, {}
            else:
                TCMtoDB.node_creation("annotation_optional")
                return ["annotation_optional"], {}
        
        query = """MATCH (sroot: SpecificationNode) WHERE NOT (sroot)<-[:CONTAINS]-()
MATCH (a:AnnotationNode {annotation: 'This value is optional'})-[:ANNOTATES]->(s)
MATCH p = (sroot)-[:CONTAINS*]->(s) WITH collect(s.name) as non_existent_nodes, reduce(acc = "root", n in nodes(p)[1..-1]| acc + '.' + n.name) as ne_nodes_path
RETURN non_existent_nodes, ne_nodes_path"""
        result2 = session.run(query)
        return result, {path: names for names, path in result2}
        
    @staticmethod
    def get_db_spec_nodes_paths(session):
        query = """MATCH (sroot:SpecificationNode) WHERE NOT (sroot)<-[:CONTAINS]-()
MATCH p = (sroot)-[:CONTAINS*]->(s:SpecificationNode)
WITH elementId(s) as e_id, reduce(acc = 'root', n in nodes(p)[1..-1]|acc + '.' + n.name) as mother_path, nodes(p)[-1].name as last_name
RETURN e_id, mother_path, mother_path+'.'+last_name"""
        result = session.run(query)
        return {path: (e_id, mother_path) for e_id, mother_path, path in result}


    ################# Utils ####################

    @staticmethod
    def is_from_db(db_identifier: str|list|None)->bool:
        return db_identifier is not None and not isinstance(db_identifier, list)
    
    @staticmethod
    def get_db_s_root():
        for node in TCMtoDB.db_info["db_specification_nodes"].keys():
            if node["name"] == "root":
                return node
        raise Exception("[CRITICAL ERROR] no root node found in the db, must have name 'root'")
    

    ################## Processing node type ###########################

    @staticmethod
    def process_type_db(current_node: Node, db_sn_element)->None:
        current_node_valtype = locate(current_node.get_stype())
        db_sn_type = locate(db_sn_element['type'])
        if db_sn_element.element_id in TCMtoDB.final_queries["type_change"] and TYPES[TCMtoDB.final_queries["type_change"][db_sn_element.element_id]] > TYPES[db_sn_type]:
            db_sn_type = TCMtoDB.final_queries["type_change"][db_sn_element.element_id]
        if db_sn_type == current_node_valtype: return
        if TYPES[db_sn_type] < TYPES[current_node_valtype]:
            TCMtoDB.final_queries["type_change"][db_sn_element.element_id] = TCMtoDB.update_tsm_types_query(db_sn_element, current_node, db_sn_type, current_node_valtype)
        else:
            current_node.cast(db_sn_type)
        
    @staticmethod
    def update_tsm_types_query(db_sn_element, current_node: Node, db_sn_type, current_node_valtype: type)->str:
        update_sn_query = f"""MATCH (sn:SpecificationNode) WHERE elementId(sn) = '{db_sn_element.element_id}'
SET sn.type = '{current_node.get_stype()}' WITH sn\n"""
        cast_method = "n.value"
        if db_sn_type == bool:
            cast_method = TCMtoDB.Neo4j_type_cast(cast_method, int)
        if current_node_valtype == float:
            cast_method = TCMtoDB.Neo4j_type_cast(cast_method, float)
        elif current_node_valtype == str:
            cast_method = TCMtoDB.Neo4j_type_cast(cast_method, str)

        update_vn_query = f"""MATCH (vn:ValueNode) WHERE (sn)<-[:IS_SPECIFIED_BY]-(vn) WITH collect(vn) as value_nodes
FOREACH(n IN value_nodes | SET n.value = {cast_method})"""
        return update_sn_query + update_vn_query
        
    @staticmethod
    def Neo4j_type_cast(obj: str, cast_into: type)->str:
        if cast_into == int:
            return f"toInteger({obj})"
        elif cast_into == float:
            return f"toFloat({obj})"
        elif cast_into == str:
            return f"toString({obj})"
    
    @staticmethod
    def find_s_option(mother_specification_element: str, current_node: Node):
        for k, v in TCMtoDB.db_info["db_specification_nodes"].items():
            if k.element_id == mother_specification_element:
                for child_k in TCMtoDB.db_info["db_specification_nodes"].keys():
                    if child_k["name"] == current_node.name() and child_k.element_id[39:] in v:
                        return child_k
        return None
        
        
    ############### queries to create objects in db ################

    @staticmethod
    def node_creation(*args)->None:
        TCMtoDB.final_queries["node_creation"].append(tuple(args))
        TCMtoDB.nodes_created.append(args[0])

    @staticmethod
    def edge_creation(ms_element: str|list, cs_element: str|list, relation: str, relation_index: list[int] = None)->None:
        identifiers = [None, None]
        for i, e in enumerate([ms_element, cs_element]):
            if isinstance(e, str): #db node
                if e in TCMtoDB.final_queries["node_matching"]:
                    identifiers[i] = TCMtoDB.final_queries["node_matching"][e]
                else:
                    identifiers[i] = TCMtoDB.final_queries["node_matching"][e] = f'e{len(TCMtoDB.final_queries["node_matching"])}'
            elif isinstance(e, list): #new node
                identifiers[i] = e[0]
            
        TCMtoDB.final_queries["edge_creation"].append((*identifiers, relation, relation_index))
    
    
    ################ processing queries ############################
    
    @staticmethod
    def process_final_queries(session)->None:
        query = ""
        if TCMtoDB.final_queries["type_change"] != {}:      query += TCMtoDB.type_change_query()+"\n"
        if TCMtoDB.final_queries["node_matching"] != {}:    query += TCMtoDB.node_matching_query()+"\n"
        if TCMtoDB.final_queries["node_creation"] != []:    query += TCMtoDB.node_creation_query()+"\n"
        if TCMtoDB.final_queries["edge_creation"] != []:    query += TCMtoDB.edge_creation_query()+"\n"
        query += TCMtoDB.file_annotation_query()
        
        session.run(query)
    
    @staticmethod
    def node_matching_query()->str:
        queries = []
        for db_node_eid, ref_id in TCMtoDB.final_queries["node_matching"].items():
            queries.append(f"MATCH ({ref_id}) WHERE elementId({ref_id}) = '{db_node_eid}'")
        
        return reduce(lambda x, y: x+"\n"+y, queries)

    @staticmethod
    def node_creation_query()->str:
        queries = []
        for n_tuple in TCMtoDB.final_queries["node_creation"]:
            match len(n_tuple):
                case 1:
                    identifier, = n_tuple
                    queries.append(f"CREATE ({identifier}:AnnotationNode {{annotation: 'This value is optional'}})")
                case 2:
                    identifier, value = n_tuple
                    queries.append(f"CREATE ({STARTING_CHAR}{identifier}:ValueNode {{identifier: '{identifier}', value: {sanitize(value)}}})")
                case 3:
                    identifier, name, stype = n_tuple
                    queries.append(f"CREATE ({identifier}:SpecificationNode {{name: '{name}', type: '{stype}'}})")
                case _:
                    raise Exception("parameters for node creation not valid")

        return reduce(lambda x, y: x+"\n"+y, queries)

    @staticmethod
    def type_change_query()->str:
        return reduce(lambda x, y: x +"\n"+y, TCMtoDB.final_queries["type_change"].values())
    
    @staticmethod
    def edge_creation_query()->str:
        queries = []
        for edge in TCMtoDB.final_queries["edge_creation"]:
            mother_id, child_id, relation, relation_index = edge
            index_str = f" {{index: {relation_index}}}" if relation_index is not None else "" 
            queries.append(f"CREATE ({mother_id})-[:{relation}{index_str}]->({child_id})")
        
        return reduce(lambda x, y: x+"\n"+y, queries)
        
    @staticmethod
    def file_annotation_query():
        root_id, filename_list = list(TCMtoDB.tcm_annotations["filenames"].items())[0]
        return f"CREATE (:FileNode:AnnotationNode {{filenames: {filename_list}}})-[:ANNOTATES]->({STARTING_CHAR}{root_id}) \n"
    
    @staticmethod
    def annotation_tcm_in_db_query(root_identifier): # root is known to be in the graph
        file_name = TCMtoDB.tcm_annotations["filenames"][root_identifier][0]
        return f"""MATCH (f:FileNode) WHERE (f)-[:ANNOTATES]->(:ValueNode {{identifier: '{root_identifier}'}})
SET f.filenames = f.filenames + '{file_name}'"""



def main():
    URI = "bolt://localhost:7687"
    AUTH = ("neo4j", "password")
    DB_NAME = AUTH[0]
    json_path = "arc_json"
    
    files_to_consider = ['Mahyco_0x5b67d7517e00.json', 'Mahyco_0x5aa3a2f6d0f0.json', 'Mahyco_0x5be0ee5cb7b0.json']
    processed_json = []
    for filename in files_to_consider:
        file_path = os.path.join(json_path, filename)
        print(file_path)
        processed_json.append(TCM(file_path, 'mahyco'))
    

    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        driver.verify_connectivity()
        driver.execute_query("MATCH (p)\nDETACH DELETE p")# remove current graph
        for tcm in processed_json:
            TCMtoDB.expand_neo4j_tsm(driver, DB_NAME, tcm)
            print("-------------------------------------")
        
    return


    query = f"""MATCH (SNM:SpecificationNode)<-[:IS_SPECIFIED_BY]-(:ValueNode {{identifier: "a1566f82ecbad4341fdb52a472e4c5b1"}})
            OPTIONAL MATCH (SN:SpecificationNode {{name: "name"}})<-[:CONTAINS]-(SNM)
            RETURN SNM, SN
            """
    test = driver.execute_query(query)
    print(test[0]) #records
    print(test[0][0]) # first of records if multiple possibilities
    print(test[0][0][0]) # first return value of query
    print(test[0][0][0].element_id)
    print(test[0][0][1])

        

if __name__ == "__main__":
    args = sys.argv
    if len(args) == 1: main()
    elif args[1] == 'test':
        import tests.test_tcm_to_neo4j as test
        test.validate_db_from_tcm()