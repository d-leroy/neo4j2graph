import argparse
import logging
import os
import sys
from neo4j import GraphDatabase
from panoramix.tcm_to_tsm import TSM
from panoramix.json_to_tcm import TCM

logger = logging.getLogger(__name__)

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


def build_tsm(files, json_path):
    processed_json = []
    skipped_files = []

    # Phase 1: parse all files into TCMs
    for filename in files:
        file_path = os.path.join(json_path, filename)
        logger.info("Parsing %s", file_path)
        try:
            tcm = TCM(file_path)
            processed_json.append(tcm)
            logger.debug("Parsed TCM from %s", filename)
        except Exception as exc:
            logger.error("SKIPPED %s: %s", filename, exc)
            skipped_files.append((filename, str(exc)))

    if not processed_json:
        raise ValueError("No files were successfully parsed.")

    # Phase 2: build TSM incrementally, file by file
    tsm = TSM([])  # start empty
    for tcm in processed_json:
        try:
            tsm.expand_tsm(tcm)
        except (TypeError, ValueError, KeyError) as exc:
            logger.error(
                "TSM rejected file %s: %s",
                os.path.basename(tcm.file_path), exc
            )
            skipped_files.append((os.path.basename(tcm.file_path), str(exc)))

    return tsm, skipped_files

def _confirm_delete():
    prompt = input(
        "WARNING: This will DELETE ALL DATA in the Neo4j database.\n"
        "Type DELETE to confirm, or anything else to abort: "
    )
    cleaned = prompt.replace("\r", "").strip()
    if cleaned == "DELETE":
        return True
    logger.info("\"%s\" != \"DELETE\" — abort.", cleaned)
    return False

def populate_neo4j(files, json_path, neo4j_uri, neo4j_user, neo4j_password, delete=False):
    if delete and not _confirm_delete():
        logger.info("Delete cancelled. Exiting without making changes.")
        return []

    logger.info("Parsing JSON files...")
    logger.info("Parsing %d JSON file(s) from %s", len(files), json_path)
    tsm, skipped = build_tsm(files, json_path=json_path)
    string_for_neo4j = TSM_creation_query(tsm)

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    try:
        driver.verify_connectivity()

        if delete:
            with driver.session() as session:
                session.run("MATCH (p) DETACH DELETE p").consume()
            logger.info("Deleted all existing nodes from database")
        else:
            logger.info("Keeping existing database (--delete not set)")

        with driver.session() as session:
            session.run(string_for_neo4j).consume()
        logger.info("Cypher import finished")
    finally:
        driver.close()
        logger.info("Neo4j driver closed")

    if skipped:
        logger.warning("SKIPPED %d file(s):", len(skipped))
        for filename, reason in skipped:
            logger.warning("  - %s: %s", filename, reason)

    return skipped

def main():
    parser = argparse.ArgumentParser(description="Build TSM from JSON and import into Neo4j")
    parser.add_argument("--json-path", required=True, help="Directory containing JSON files")
    parser.add_argument("--neo4j-uri", default="bolt://neo4j:7687", help="Neo4j connection URI (default: bolt://neo4j:7687)")
    parser.add_argument("--neo4j-user", default="neo4j", help="Neo4j username (default: neo4j)")
    parser.add_argument("--neo4j-password", default="password", help="Neo4j password (default: password)")
    parser.add_argument("--populate", action="store_true", help="Import all JSON files in the directory")
    parser.add_argument("--delete", action="store_true", help="Delete all existing database content before import (requires interactive confirmation)")
    parser.add_argument("files", nargs="*", help="Specific JSON filenames to import (requires --json-path)")

    args = parser.parse_args()

    if args.populate:
        files = [filename for filename in os.listdir(args.json_path) if filename.endswith(".json")]
        populate_neo4j(files, args.json_path, args.neo4j_uri, args.neo4j_user, args.neo4j_password, delete=args.delete)
    elif args.files:
        populate_neo4j(args.files, args.json_path, args.neo4j_uri, args.neo4j_user, args.neo4j_password, delete=args.delete)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
