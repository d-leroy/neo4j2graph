from panoramix.neo4j_graph_functions import GraphFunctions
from neo4j import GraphDatabase
from tests.test_tcm_to_tsm import test_tsm

def validate_db(by_query = True):
    URI = "bolt://localhost:7687"
    AUTH = (os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
    DB_NAME = AUTH[0]

    with GraphDatabase.driver(URI, auth=AUTH, encrypted=False) as driver:
        driver.verify_connectivity()

        with driver.session(database = DB_NAME) as session:
            if by_query:    db_validity = session.run(GraphFunctions.Db_Validity_query()).single()
            else:           tsm = GraphFunctions.TSM_from_db(session)
    
    if by_query:    assert db_validity[0] == True
    else:           test_tsm(tsm)
    print('ALL tests validated')
