from panoramix.tcm_to_neo4j import *
from panoramix.tcm_to_tsm import TSM, VNode, SNode, Edge
import os
from panoramix.neo4j_graph_functions import GraphFunctions as gf
import neo4j.graph as ng

def to_identifiers(*lists):
    ret = []
    for l in lists:
        ret.append(to_identifier(l))
    return ret

def to_identifier(obj):
    if isinstance(obj, VNode):
        return obj.get_identifier()
    elif isinstance(obj, SNode):
        return f"{obj.name()}:{obj.stype_name()}"
    elif isinstance(obj, Edge):
        return [to_identifier(obj.source()), to_identifier(obj.target())]
    elif isinstance(obj, ng.Node):
        if "ValueNode" in obj.labels:
            return obj['identifier']
        elif "SpecificationNode" in obj.labels:
            return f'{obj["name"]}:{obj["type"]}'
    elif isinstance(obj, list):
        return [to_identifier(o) for o in obj]

def check_ids(*lists):
    for db_list, tsm_list in lists:
        for node_element_id in db_list:
            assert node_element_id in tsm_list
            tsm_list.remove(node_element_id)

def verify_db_tsm(tsm, query_result):
    vn, sn, ce, se = to_identifiers(*tsm.get_model())
    db_vn, db_sn, db_ce, db_se = to_identifiers(*[e for e in query_result[0][0]])

    assert len(vn) == len(db_vn) and len(sn) == len(db_sn) and len(ce) == len(db_ce) and len(se) == len(db_se)
    check_ids((db_vn, vn), (db_sn, sn), (db_ce, ce), (db_se, se))

def validate_db_from_tcm():
    json_path = "arc_json/arc_json_tests"
    processed_json = []
    for filename in os.listdir(json_path):
        if filename.endswith(".json"):
            print(filename)
            file_path = os.path.join(json_path, filename)
            processed_json.append(TCM(file_path, 'mahyco'))

    tsm = TSM(processed_json)

    URI = "bolt://localhost:7687"
    AUTH = (os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
    DB_NAME = AUTH[0]

    with GraphDatabase.driver(URI, auth=AUTH, encrypted=False) as driver:
        driver.verify_connectivity()
        driver.execute_query("MATCH (p)\nDETACH DELETE p") # remove current graph
        for tcm in processed_json: # build graph here
            TCMtoDB.expand_neo4j_tsm(driver, DB_NAME, tcm)
        result = driver.execute_query(gf.get_TSM_query())
        verify_db_tsm(tsm, result)
        
    print("ALL tests validated")