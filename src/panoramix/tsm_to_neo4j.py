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

def edge_creation_query(edge, relation, tsm, new_v_ids, new_s_ids):
    list_index = f" {{listIndex: {edge.get_index()}}}" if edge.get_index() is not None else ""
    src, tgt = edge.source(), edge.target()
    src_parts = _node_ref(src, tsm, "src", new_v_ids, new_s_ids)
    tgt_parts = _node_ref(tgt, tsm, "tgt", new_v_ids, new_s_ids)
    clauses = []
    if src_parts["match"]:
        clauses.append(src_parts["match"])
    if tgt_parts["match"]:
        clauses.append(tgt_parts["match"])
    clauses.append(f"CREATE ({src_parts['var']})-[{relation}{list_index}]->({tgt_parts['var']})")
    return " ".join(clauses)

def _node_ref(node, tsm, var, new_v_ids, new_s_ids):
    from panoramix.tcm_to_tsm import VNode, SNode
    if isinstance(node, VNode):
        if node.get_identifier() in new_v_ids:
            return {"match": "", "var": f"{STARTING_CHAR}{node.get_identifier()}"}
        return {"match": f"MATCH ({var}:ValueNode {{identifier: {sanitize(node.get_identifier())}}})", "var": var}
    else:
        if id(node) in new_s_ids:
            return {"match": "", "var": f"{STARTING_CHAR}{node.get_identifier()}"}
        path = tsm.get_s_node_path(node)
        parts = path.split(".")
        nodes = []
        for i, p in enumerate(parts):
            name = var if i == len(parts) - 1 else f"_{var}_{i}"
            nodes.append(f"({name}:SpecificationNode {{name: {sanitize(p)}}})")
        chain = "-[:CONTAINS]->".join(nodes)
        return {"match": f"MATCH {chain}", "var": var}

def file_annotation_creation_query(node_id, file_names):
    return f"MATCH (n:ValueNode {{identifier: {sanitize(node_id)}}}) CREATE (:FileNode:AnnotationNode {{filenames: {file_names}, annotation: null}})-[:ANNOTATES]->(n)"

def _match_s_node_by_path(path):
    parts = path.split(".")
    nodes = []
    for i, p in enumerate(parts):
        name = "target" if i == len(parts) - 1 else f"_target_{i}"
        nodes.append(f"({name}:SpecificationNode {{name: {sanitize(p)}}})")
    chain = "-[:CONTAINS]->".join(nodes)
    return f"MATCH {chain}"

def optional_node_annotation_creation_query(s_node_path):
    return f"{_match_s_node_by_path(s_node_path)} MATCH (cannotationnode:AnnotationNode {{annotation: 'This value is optional'}}) CREATE (cannotationnode)-[:ANNOTATES]->(target)"

def nonexistant_node_creation_query(parent_id, name):
    return f"MATCH (parent:ValueNode {{identifier: {sanitize(parent_id)}}}) MATCH (cannotationnode:AnnotationNode {{annotation: 'This value is optional'}}) CREATE (cannotationnode)-[:ANNOTATES]->(:SpecificationNode {{name: '{name}', type: 'bool'}})<-[:CONTAINS]-(parent)"

def TSM_creation_query(tsm):
    query = ""
    new_v_ids = {n.get_identifier() for n in tsm.get_value_nodes()}
    new_s_ids = {id(n) for n in tsm.get_specification_nodes()}

    for node in tsm.get_value_nodes():          query += v_node_creation_query(node) + "\n"
    for node in tsm.get_specification_nodes():  query += s_node_creation_query(node) + "\n"
    for edge in tsm.get_containment_edges():    query += edge_creation_query(edge, ":CONTAINS", tsm, new_v_ids, new_s_ids) + "\n"
    for edge in tsm.get_specification_edges():  query += edge_creation_query(edge, ":IS_SPECIFIED_BY", tsm, new_v_ids, new_s_ids) + "\n"
    
    nb_optional_nodes = len(tsm.get_annotations()["optional_nodes"]) + len(tsm.get_annotations()["nonexistent_nodes"])
    if nb_optional_nodes > 0: query += "MERGE (cannotationnode:AnnotationNode {annotation: 'This value is optional'})"

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


def _diff_annotations(prev, curr):
    """Return only new/changed annotation entries in curr vs prev."""
    diff = {}
    for key in ("filenames", "optional_nodes", "nonexistent_nodes"):
        prev_val = prev.get(key, {})
        curr_val = curr.get(key, {})
        if key in ("filenames", "optional_nodes"):
            diff[key] = {k: v for k, v in curr_val.items() if k not in prev_val}
        elif key == "nonexistent_nodes":
            diff[key] = {}
            for parent_id, names in curr_val.items():
                if parent_id not in prev_val:
                    diff[key][parent_id] = names
                else:
                    new_names = [n for n in names if n not in prev_val[parent_id]]
                    if new_names:
                        diff[key][parent_id] = new_names
    return diff


def TSM_creation_query_batch(v_nodes, s_nodes, c_edges, s_edges, annotations, tsm):
    query = ""
    new_v_ids = {n.get_identifier() for n in v_nodes}
    new_s_ids = {id(n) for n in s_nodes}

    for node in v_nodes:       query += v_node_creation_query(node) + "\n"
    for node in s_nodes:       query += s_node_creation_query(node) + "\n"
    for edge in c_edges:       query += edge_creation_query(edge, ":CONTAINS", tsm, new_v_ids, new_s_ids) + "\n"
    for edge in s_edges:       query += edge_creation_query(edge, ":IS_SPECIFIED_BY", tsm, new_v_ids, new_s_ids) + "\n"

    nb_optional = len(annotations.get("optional_nodes", {})) + len(annotations.get("nonexistent_nodes", {}))
    if nb_optional > 0: query += "MERGE (cannotationnode:AnnotationNode {annotation: 'This value is optional'})\n"

    for key in ("filenames", "optional_nodes", "nonexistent_nodes"):
        annotation = annotations.get(key, {})
        if not annotation:
            continue
        if key == "filenames":
            for root_id, filenames in annotation.items():
                query += file_annotation_creation_query(root_id, filenames) + "\n"
        elif key == "optional_nodes":
            for spec_node_id in annotation:
                query += optional_node_annotation_creation_query(spec_node_id) + "\n"
        elif key == "nonexistent_nodes":
            for parent_id, names in annotation.items():
                for option_name in names:
                    query += nonexistant_node_creation_query(parent_id, option_name) + '\n'

    return query.rstrip()


def build_tsm(files, json_path, data_key=None):
    processed_json = []
    skipped_files = []

    # Phase 1: parse all files into TCMs
    for filename in files:
        file_path = os.path.join(json_path, filename)
        logger.info("Parsing %s", file_path)
        try:
            tcm = TCM(file_path, data_key)
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

def populate_neo4j(files, json_path, neo4j_uri, neo4j_user, neo4j_password, delete=False, data_key=None):
    if delete and not _confirm_delete():
        logger.info("Delete cancelled. Exiting without making changes.")
        return []

    logger.info("Parsing JSON files...")
    logger.info("Parsing %d JSON file(s) from %s", len(files), json_path)

    # Phase 1: parse all files into TCMs
    processed_json = []
    skipped = []
    for filename in files:
        file_path = os.path.join(json_path, filename)
        logger.info("Parsing %s", file_path)
        try:
            tcm = TCM(file_path, data_key)
            processed_json.append(tcm)
            logger.debug("Parsed TCM from %s", filename)
        except Exception as exc:
            logger.error("SKIPPED %s: %s", filename, exc)
            skipped.append((filename, str(exc)))

    if not processed_json:
        raise ValueError("No files were successfully parsed.")

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    try:
        driver.verify_connectivity()

        if delete:
            with driver.session() as session:
                session.run("MATCH (p) DETACH DELETE p").consume()
            logger.info("Deleted all existing nodes from database")
        else:
            logger.info("Keeping existing database (--delete not set)")

        # Phase 2: build TSM and import incrementally, one batch per TCM
        from panoramix.neo4j_graph_functions import GraphFunctions
        logger.info("Starting incremental import: %d TCM(s) to process", len(processed_json))
        tsm = TSM([])
        for i, tcm in enumerate(processed_json, 1):
            filename = os.path.basename(tcm.file_path)
            try:
                prev_v = len(tsm.get_value_nodes())
                prev_s = len(tsm.get_specification_nodes())
                prev_c = len(tsm.get_containment_edges())
                prev_se = len(tsm.get_specification_edges())
                prev_ann = {k: dict(v) for k, v in tsm.get_annotations().items()}

                tsm.expand_tsm(tcm)

                new_v = tsm.get_value_nodes()[prev_v:]
                new_s = tsm.get_specification_nodes()[prev_s:]
                new_c = tsm.get_containment_edges()[prev_c:]
                new_se = tsm.get_specification_edges()[prev_se:]
                new_ann = _diff_annotations(prev_ann, tsm.get_annotations())

                batch_query = TSM_creation_query_batch(new_v, new_s, new_c, new_se, new_ann, tsm)
                if batch_query:
                    with driver.session() as session:
                        session.run(batch_query).consume()
                        validity_record = session.run(GraphFunctions.Db_Validity_query()).single()
                        is_valid = validity_record[0] if validity_record else None
                        if not is_valid:
                            details_record = session.run(GraphFunctions.Db_Validity_details_query()).single()
                            checks = details_record[0] if details_record else {}
                            failed_checks = [name for name, passed in checks.items() if not passed]
                            logger.debug("Validation checks: %s", dict(checks))
                            for name, passed in checks.items():
                                if not passed:
                                    logger.debug("  FAILED check: %s", name)
                            diag_record = session.run(GraphFunctions.Db_Validity_diagnostic_query()).single()
                            diagnostics = diag_record[0] if diag_record else {}
                            logger.debug("Diagnostics: %s", diagnostics)
                    logger.info("[%d/%d] %s: imported %d VNodes, %d SNodes, %d CEdges, %d SEdges",
                                i, len(processed_json), filename,
                                len(new_v), len(new_s), len(new_c), len(new_se))
                    if is_valid:
                        logger.info("[%d/%d] %s: database validation passed",
                                    i, len(processed_json), filename)
                    else:
                        raise RuntimeError(
                            f"Database validation failed after importing {filename} "
                            f"[{i}/{len(processed_json)}]: failed checks: {', '.join(failed_checks)}"
                        )
                else:
                    logger.info("[%d/%d] %s: nothing new to import", i, len(processed_json), filename)

            except (TypeError, ValueError, KeyError) as exc:
                logger.error("TSM rejected file %s: %s", filename, exc)
                skipped.append((filename, str(exc)))

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
    parser.add_argument("--data-key", default=None, help="Key to locate the real payload within the JSON structure (default: None, uses the whole file)")
    parser.add_argument("files", nargs="*", help="Specific JSON filenames to import (requires --json-path)")

    args = parser.parse_args()

    if args.populate:
        files = [filename for filename in os.listdir(args.json_path) if filename.endswith(".json")]
        populate_neo4j(files, args.json_path, args.neo4j_uri, args.neo4j_user, args.neo4j_password, delete=args.delete, data_key=args.data_key)
    elif args.files:
        populate_neo4j(args.files, args.json_path, args.neo4j_uri, args.neo4j_user, args.neo4j_password, delete=args.delete, data_key=args.data_key)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
