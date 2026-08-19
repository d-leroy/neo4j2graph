#!/usr/bin/env python3
"""Panoramix MCP server exposing read-only graph analytics over Neo4j."""

import os
from contextlib import contextmanager
from typing import Any, Dict, List, Union

from neo4j import GraphDatabase
from neo4j.graph import Node as Neo4jNode, Relationship as Neo4jRelationship

from fastmcp import FastMCP

from panoramix.neo4j_graph_functions import GraphFunctions

mcp = FastMCP("panoramix")


def _neo4j_config() -> tuple[str, tuple[str, str], str]:
    """Read Neo4j connection settings from env (with defaults)."""
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "password")
    database = os.environ.get("NEO4J_DATABASE", "neo4j")
    return uri, (user, password), database


@contextmanager
def _session():
    """Yield a Neo4j session, cleaning up the driver on exit."""
    uri, auth, database = _neo4j_config()
    driver = GraphDatabase.driver(uri, auth=auth)
    try:
        driver.verify_connectivity()
        with driver.session(database=database) as session:
            yield session
    finally:
        driver.close()


def _serialize(obj: Any) -> Any:
    """Recursively serialize Neo4j nodes/relationships to plain JSON-friendly dicts."""
    if isinstance(obj, Neo4jNode):
        data = dict(obj)
        data["_element_id"] = obj.element_id
        data["_labels"] = list(obj.labels)
        return data
    if isinstance(obj, Neo4jRelationship):
        data = dict(obj)
        data["_element_id"] = obj.element_id
        data["_type"] = obj.type
        data["_start_node"] = obj.start_node.element_id if hasattr(obj.start_node, "element_id") else None
        data["_end_node"] = obj.end_node.element_id if hasattr(obj.end_node, "element_id") else None
        return data
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


def _result_to_list(result) -> list[dict]:
    """Convert a neo4j Result to a list of plain dicts."""
    return [_serialize(record.data()) for record in result]


@mcp.tool()
def get_database_summary() -> dict:
    """Return a quick count of nodes grouped by their primary label."""
    with _session() as session:
        result = session.run(
            "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY count DESC"
        )
        return {record["label"]: record["count"] for record in result}


@mcp.tool()
def option_coverage(s_node_identifying_component: Union[str, dict]) -> list[dict]:
    """
    Query option coverage for a given specification node.

    Args:
        s_node_identifying_component: either a Neo4j elementId string
            (e.g. "4:ff0859ac-496c-403c-b1cb-8a0bb1eafbc9:1543")
            or a dict of identifying properties (e.g. {"name": "final_time", "type": "float"}).
    """
    with _session() as session:
        return _result_to_list(GraphFunctions.option_coverage(session, s_node_identifying_component))


@mcp.tool()
def combinatorial_coverage(
    leaf_nodes_to_consider: Union[List[Union[str, dict]], str] = None,
    with_auto_reference_on_lists: bool = False,
) -> list[dict]:
    """
    Generate combinatorial coverage relationships among leaf ValueNodes.

    Args:
        leaf_nodes_to_consider: list of node identifiers (elementId strings or property dicts)
            to restrict the analysis to, or omit for "ALL".
        with_auto_reference_on_lists: if True, include list-internal auto-references.
    """
    if leaf_nodes_to_consider is None:
        leaf_nodes_to_consider = "ALL"
    with _session() as session:
        return _result_to_list(
            GraphFunctions.combinatorial_coverage(
                session, leaf_nodes_to_consider, with_auto_reference_on_lists
            )
        )


@mcp.tool()
def tsm_slicing(
    nodes_to_find_on_single_root: List[Union[str, dict]],
    return_all_subgraphs: bool = False,
) -> list[dict]:
    """
    Slice the TSM graph to keep only paths that contain the specified leaf nodes.

    Args:
        nodes_to_find_on_single_root: leaf node identifiers to match.
        return_all_subgraphs: if True, do not restrict to a single root.
    """
    with _session() as session:
        return _result_to_list(
            GraphFunctions.TSM_Slicing(
                session, nodes_to_find_on_single_root, return_all_subgraphs
            )
        )


@mcp.tool()
def tsm_slicing_and_combinatorial_coverage(
    nodes_on_slice: List[Union[str, dict]],
    nodes_for_combinatorial_coverage: Union[List[Union[str, dict]], str] = None,
    return_all_subgraphs: bool = False,
    with_self_reference: bool = False,
) -> list[dict]:
    """
    First slice the TSM by `nodes_on_slice`, then compute combinatorial coverage
    on the remaining leaf nodes.

    Args:
        nodes_on_slice: leaf identifiers used for the slicing step.
        nodes_for_combinatorial_coverage: leaf identifiers for the coverage step,
            or omit/None for "ALL".
        return_all_subgraphs: passed through to the slicing step.
        with_self_reference: passed through to the coverage step.
    """
    if nodes_for_combinatorial_coverage is None:
        nodes_for_combinatorial_coverage = "ALL"
    with _session() as session:
        return _result_to_list(
            GraphFunctions.TSM_Slicing_and_Combinatorial_Coverage(
                session,
                nodes_on_slice,
                nodes_for_combinatorial_coverage,
                return_all_subgraphs,
                with_self_reference,
            )
        )


@mcp.tool()
def compute_prevalence(compute_with_occurrence: bool = True) -> dict:
    """
    Compute node prevalence (harmonic mean of leaf properties) for internal ValueNodes.

    Args:
        compute_with_occurrence: use occurrence counts instead of stored prevalence.
    """
    with _session() as session:
        return GraphFunctions.prevalence_without_optional_values(
            session,
            compute_with_occurrence=compute_with_occurrence,
            set_leaves_occurrences=False,
            set_in_db=False,
        )


@mcp.tool()
def validate_database() -> dict:
    """Run the built-in structural validity query and return the results."""
    with _session() as session:
        record = session.run(GraphFunctions.Db_Validity_query()).single()
        return {"is_valid": record[0] if record else None}


@mcp.tool()
def reconstruct_tsm_from_db() -> dict:
    """Pull the full TSM back from Neo4j and return a serializable summary."""
    with _session() as session:
        tsm = GraphFunctions.TSM_from_db(session)
    return {
        "value_node_count": len(tsm.get_value_nodes()),
        "specification_node_count": len(tsm.get_specification_nodes()),
        "containment_edge_count": len(tsm.get_containment_edges()),
        "specification_edge_count": len(tsm.get_specification_edges()),
        "annotations": {
            k: (
                {str(kk): vv for kk, vv in v.items()}
                if isinstance(v, dict)
                else v
            )
            for k, v in tsm.get_annotations().items()
        },
        "value_nodes": [
            {"identifier": n.get_identifier(), "value": n.val()}
            for n in tsm.get_value_nodes()
        ],
        "specification_nodes": [
            {"name": n.name(), "type": n.stype_name()}
            for n in tsm.get_specification_nodes()
        ],
    }


@mcp.resource("schema://node-labels")
def node_labels_resource() -> str:
    """Return the list of distinct node labels in the database."""
    with _session() as session:
        result = session.run("CALL db.labels() YIELD label RETURN collect(label) AS labels")
        labels = result.single()["labels"]
    return "\n".join(sorted(labels))


@mcp.resource("schema://relationship-types")
def relationship_types_resource() -> str:
    """Return the list of distinct relationship types in the database."""
    with _session() as session:
        result = session.run("CALL db.relationshipTypes() YIELD relationshipType RETURN collect(relationshipType) AS types")
        types = result.single()["types"]
    return "\n".join(sorted(types))


def main():
    mcp.run()


if __name__ == "__main__":
    main()
