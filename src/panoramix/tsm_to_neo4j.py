import os
import sys
from neo4j import GraphDatabase
from panoramix.tcm_to_tsm import TSM
from panoramix.json_to_tcm import TCM

STARTING_CHAR = "a"

def sanitize(obj):
    if obj is None: return "null"
    if isinstance(obj, str): return f"\'{obj}\'"
    return obj

def v_node_creation_query(node):
    return f"CREATE ({STARTING_CHAR}{node.get_identifier()}:ValueNode {{value: {sanitize(node.val())}, identifier: {sanitize(node.get_identifier())}}})"
    #                 ^^^^^^^^^^^^^ -- to make it so the identifier does not start with a number, neo4j does not like it

def s_node_creation_query(node):
    return f"CREATE ({STARTING_CHAR}{node.get_identifier()}:SpecificationNode {{name: {sanitize(node.name())}, type: {sanitize(node.stype_name())}}})"

def edge_creation_query(edge, relation):
    list_index = f" {{listIndex: {edge.get_index()}}}" if edge.get_index() is not None else ""
    return f"CREATE ({STARTING_CHAR}{edge.source().get_identifier()})-[{relation}{list_index}]->({STARTING_CHAR}{edge.target().get_identifier()})"

def file_annotation_creation_query(node_id, file_names):
    return f"CREATE (:FileNode:AnnotationNode {{filenames: {file_names}, annotation: null}})-[:ANNOTATES]->({STARTING_CHAR}{node_id})"

def optional_node_annotation_creation_query(s_node_id):
    return f"CREATE (cannotationnode)-[:ANNOTATES]->({STARTING_CHAR}{s_node_id})"

def nonexistant_node_creation_query(parent_id, name):
    return f"CREATE (cannotationnode)-[:ANNOTATES]->(:SpecificationNode {{name: '{name}', type: 'bool'}})<-[:CONTAINS]-({STARTING_CHAR}{parent_id})"

def TSM_creation_query(tsm):
    query = ""

    for node in tsm.get_value_nodes():          query += v_node_creation_query(node) + "\n"
    for node in tsm.get_specification_nodes():  query += s_node_creation_query(node) + "\n"
    for edge in tsm.get_containment_edges():    query += edge_creation_query(edge, ":CONTAINS") + "\n"
    for edge in tsm.get_specification_edges():  query += edge_creation_query(edge, ":IS_SPECIFIED_BY") + "\n"
    
    nb_optional_nodes = len(tsm.get_annotations()["optional_nodes"]) + len(tsm.get_annotations()["nonexistent_nodes"])
    if nb_optional_nodes > 0: query += "CREATE (cannotationnode:AnnotationNode {annotation: 'This value is optional'})"

    for key, annotation in tsm.get_annotations().items():
        match key:
            case "filenames":
                for root_id, filenames in annotation.items():
                    query += file_annotation_creation_query(root_id, filenames) + "\n"
            case "optional_nodes":
                for spec_node_id, _ in annotation.items():
                    query += optional_node_annotation_creation_query(spec_node_id) + "\n"
            case "nonexistent_nodes":
                for parent_id, name in annotation.items():
                    for option_name in name:
                        query += nonexistant_node_creation_query(parent_id, option_name) + '\n'
    
    return query[:-1]


def build_tsm(files):
    json_path = "arc_json"
    processed_json = []
    for filename in files:
        file_path = os.path.join(json_path, filename)
        print(file_path)
        test = TCM(file_path, 'mahyco')
        processed_json.append(test)
    
    return TSM(processed_json)

def main():
    test_tsm = build_tsm(['Mahyco_0x5b67d7517e00.json', 'Mahyco_0x5aa3a2f6d0f0.json', 'Mahyco_0x5be0ee5cb7b0.json'])
    #test_tsm = build_tsm(['Mahyco_0x5be0ee5cb7b0.json'])
    #test_tsm = build_tsm(['Mahyco_0x5b67d7517e00.json'])
    string_for_neo4j = TSM_creation_query(test_tsm)
    
    URI = "bolt://neo4j:7687"
    AUTH = ("neo4j", "password")

    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        driver.verify_connectivity()
        driver.execute_query("MATCH (p)\nDETACH DELETE p")# remove current graph
        print("deleted previous db")
        driver.execute_query(string_for_neo4j)# build graph here

def main_populate():
    json_path = 'arc_json'
    TCM_files = [filename for filename in os.listdir(json_path) if filename.endswith(".json")]
    test_tsm = build_tsm(TCM_files)
    string_for_neo4j = TSM_creation_query(test_tsm)

    URI = "bolt://neo4j:7687"
    AUTH = ("neo4j", "password")

    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        driver.verify_connectivity()
        driver.execute_query("MATCH (p)\nDETACH DELETE p") # remove current graph
        print("deleted previous db")
        driver.execute_query(string_for_neo4j) # build graph here
        

if __name__ == "__main__":
    args = sys.argv
    if len(args) == 1: main()
    elif args[1] == 'test':
        import tests.test_tsm_to_neo4j as test
        test.validate_db_from_TSM()
    elif args[1] == 'populate':
        main_populate()
