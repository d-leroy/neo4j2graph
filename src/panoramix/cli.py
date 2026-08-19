import os
import json
import uuid
from neo4j import GraphDatabase
from collections import defaultdict
import argparse
import xmltodict


def generate_uid():
    return str(uuid.uuid4())

def escape(name):
    return f"`{name}`"

def convert_xml_to_json(input_dir="./xml", output_dir="./arc_json"):
    """Convert XML files to JSON format."""
    os.makedirs(output_dir, exist_ok=True)
    
    converted_count = 0
    for filename in os.listdir(input_dir):
        if filename.endswith(".xml"):
            xml_path = os.path.join(input_dir, filename)
            json_path = os.path.join(output_dir, filename.replace(".xml", ".json"))

            try:
                with open(xml_path, 'r', encoding='utf-8') as xml_file:
                    data_dict = xmltodict.parse(xml_file.read())
                    with open(json_path, 'w', encoding='utf-8') as json_file:
                        json.dump(data_dict, json_file, indent=2, ensure_ascii=False)
                    print(f"Converted: {filename} → {os.path.basename(json_path)}")
                    converted_count += 1
            except Exception as e:
                print(f"Failed to convert {filename}: {e}")
    
    print(f"XML to JSON conversion complete: {converted_count} file(s) converted.")

# ---------- merge/json ingestion logic ----------

def create_index_for_labels(tx, labels):
    for label in labels:
        constraint_name = f"uid_constraint_{label}"
        query = f"""
            CREATE CONSTRAINT {escape(constraint_name)} IF NOT EXISTS 
            FOR (n:{escape(label)}) REQUIRE n.uid IS UNIQUE
        """
        tx.run(query)

def insert_all(tx, nodes, relationships):
    for node in nodes:
        label = escape(node['label'])
        query = f"""
            MERGE (n:{label} {{uid: $uid}})
            SET n += $props
        """
        tx.run(query, uid=node["uid"], props=node["properties"])

    for rel in relationships:
        from_label = escape(rel["from_label"])
        to_label = escape(rel["to_label"])
        rel_type = escape(rel["type"])
        query = f"""
            MATCH (a:{from_label} {{uid: $from_uid}})
            MATCH (b:{to_label} {{uid: $to_uid}})
            MERGE (a)-[r:{rel_type}]->(b)
        """
        tx.run(query, from_uid=rel["from"], to_uid=rel["to"])

def split_json(data, parent_uid=None, parent_label=None, rel_type=None, path=""):
    nodes = []
    relationships = []

    node_uid = generate_uid()
    node_label = path.split("TestCase/case/")[-1].lower() or path.split("/case/")[-1].lower() or "TestCase"

    props = {}
    if isinstance(data, dict):
        split_json_rec(data, path, nodes, relationships, node_uid, node_label, props)
    else:
        for d in data:
            split_json_rec(d, path, nodes, relationships, node_uid, node_label, props)

    node = {
        "uid": node_uid,
        "label": node_label,
        "properties": props
    }
    nodes.append(node)

    if parent_uid:
        relationships.append({
            "from": parent_uid,
            "to": node_uid,
            "type": rel_type,
            "from_label": parent_label,
            "to_label": node_label
        })

    return nodes, relationships

def split_json_rec(data, path, nodes, relationships, node_uid, node_label, props):
    for k, v in data.items():
        if isinstance(v, dict):
            child_nodes, child_rels = split_json(
                v, node_uid, node_label, f"{node_label.upper()}_TO_{k.upper()}", f"{path}/{k}"
            )
            nodes.extend(child_nodes)
            relationships.extend(child_rels)
        elif isinstance(v, list):
            if all(isinstance(item, dict) for item in v):
                for item in v:
                    child_nodes, child_rels = split_json(
                        item, node_uid, node_label, f"{node_label.upper()}_TO_{k.upper()}", f"{path}/{k}"
                    )
                    nodes.extend(child_nodes)
                    relationships.extend(child_rels)
            else:
                props[k] = v
        else:
            if k.lower() in {"id", "elementid"}:
                continue
            props[k] = v

def run_merge(json_path="./arc_json", neo4j_uri="bolt://localhost:7687", neo4j_username="neo4j", neo4j_password="password"):
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_username, neo4j_password))

    all_nodes = []
    all_relationships = []

    for filename in os.listdir(json_path):
        if filename.endswith(".json"):
            file_path = os.path.join(json_path, filename)
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    if isinstance(data, dict):
                        nodes, relationships = split_json(data, path="TestCase")
                        all_nodes.extend(nodes)
                        all_relationships.extend(relationships)
                except Exception as e:
                    print(f"[ERROR] Failed to parse {file_path}: {e}")

    print(f"Parsed {len(all_nodes)} nodes and {len(all_relationships)} relationships.")

    all_labels = {node["label"] for node in all_nodes}

    with driver.session() as session:
        session.execute_write(create_index_for_labels, all_labels)
        session.execute_write(insert_all, all_nodes, all_relationships)

    driver.close()
    print("All data inserted into Neo4j successfully.")

# ---------- export_axl logic ----------

class JSONToNeo4jVisitor:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.counter = 0

    def close(self):
        self.driver.close()

    def create_module(self, module_data):
        with self.driver.session() as session:
            result = session.run(
                f"CREATE (m:{str(module_data['Name'])}"+"{name: $name, type: $type, interfaces: $interfaces}) RETURN id(m)",
                {"name": module_data["Name"], "type": module_data["Type"], "interfaces": module_data["Interface"]}
            )
            return result.single()[0]  # Internal node id of the Module

    def create_option(self, session, parent_id, option_data):
        # Create node
        result = session.run(
            """
            MATCH (p) WHERE id(p) = $parent_id
            CREATE (o:Option {
                name: $name,
                type: $type,
                hasDefault: $hasDefault,
                defaultValue: $defaultValue,
                hasMinOccursAttribute: $hasMinOccursAttribute,
                minOccurs: $minOccurs,
                hasMaxOccursAttribute: $hasMaxOccursAttribute,
                maxOccurs: $maxOccurs,
                isOptional: $isOptional,
                fullName: $fullName,
                id: $id
            })
            CREATE (p)-[:HAS_OPTION]->(o)
            RETURN id(o)
            """,
            {
                "parent_id": parent_id,
                "name": option_data["Name"],
                "type": option_data["Type"],
                "hasDefault": option_data["HasDefault"],
                "defaultValue": option_data["DefaultValue"],
                "hasMinOccursAttribute": option_data["HasMinOccursAttribute"],
                "minOccurs": option_data["MinOccurs"],
                "hasMaxOccursAttribute": option_data["HasMaxOccursAttribute"],
                "maxOccurs": option_data["MaxOccurs"],
                "isOptional": option_data["IsOptional"],
                "fullName": option_data["FullName"],
                "id": option_data["Id"]
            }
        )
        return result.single()[0]  # Internal node id of the Option

    def visit_option(self, session, parent_id, option_data):
        option_id = self.create_option(session, parent_id, option_data)
        for sub_option in option_data.get("Options", []):
            self.visit_option(session, option_id, sub_option)

    def process(self, data):
        with self.driver.session() as session:
            module_id = self.create_module(data)
            for option in data.get("Options", []):
                self.visit_option(session, module_id, option)


def link_interfaces(tx):
    query = """
    MATCH (m)
    WHERE m.interfaces IS NOT NULL
    UNWIND m.interfaces AS interface_name
    MATCH (o:Option)
    WHERE interface_name = o.type
    MERGE (m)-[:IMPLEMENTS]->(o)
    """
    tx.run(query)


def create_specifies_option_relationships(tx):
    result = tx.run("MATCH (o:Option) RETURN o.fullName AS label, id(o) AS oid")
    
    for record in result:
        label = record["label"]
        oid = record["oid"]
        
        dynamic_cypher = f"""
        MATCH (n:`{label}`), (o:Option)
        WHERE id(o) = $oid
        MERGE (o)-[:SPECIFIES]->(n)
        """
        
        tx.run(dynamic_cypher, oid=oid)


def create_specifies_service_relationships(tx):
    result = tx.run("MATCH (n) WHERE n.`@name` IS NOT NULL RETURN n.`@name` AS name, id(n) as oid")
    
    for record in result:
        name = record["name"]
        oid = record["oid"]
        
        dynamic_cypher = f"""
        MATCH (n:`{name}`), (o)
        WHERE id(o) = $oid
        MERGE (n)-[:SPECIFIES]->(o)
        """
        
        tx.run(dynamic_cypher, oid=oid)


def create_specifies_module_relationships(tx):
    result = tx.run("MATCH (n) RETURN id(n) as oid, labels(n)[0] AS name")
    
    for record in result:
        name = record["name"]
        name = [word[0].upper() + word[1:] for word in name.split()][0]
        oid = record["oid"]
        
        print(name)
        dynamic_cypher = f"""
        MATCH (n:`{name}`), (o)
        WHERE id(o) = $oid AND n.type = 'module' AND id(n) <> $oid
        MERGE (n)-[:SPECIFIES]->(o)
        """
        
        tx.run(dynamic_cypher, oid=oid)

def run_export_axl(input_dir="./axl_json", neo4j_uri="bolt://localhost:7687", neo4j_username="neo4j", neo4j_password="password"):
    # import modules from axl_json the same way export_axl.py did
    for dirpath,_,files in os.walk(input_dir):
        for filename in files:
            if filename.endswith(".json"):
                json_path = os.path.join(dirpath, filename)

                with open(json_path) as f:
                    data = json.load(f)
                visitor = JSONToNeo4jVisitor(neo4j_uri, neo4j_username, neo4j_password)
                visitor.process(data)
                visitor.close()

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_username, neo4j_password))

    with driver.session() as session:
        session.execute_write(link_interfaces)
        session.execute_write(create_specifies_option_relationships)
        session.execute_write(create_specifies_service_relationships)
        session.execute_write(create_specifies_module_relationships)
    
    driver.close()
    print("AXL export imported and relationships created.")

def main():
    """Main entry point for the panoramix CLI."""
    parser = argparse.ArgumentParser(description="Convert XML to JSON and merge data into Neo4j")
    parser.add_argument("--xml-path", default="./xml", help="Path to XML input directory")
    parser.add_argument("--json-path", default="./arc_json", help="Path to JSON directory (output for conversion, input for merge)")
    parser.add_argument("--skip-convert", action="store_true", help="Skip XML to JSON conversion step")
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687", help="Neo4j connection URI")
    parser.add_argument("--neo4j-username", default="neo4j", help="Neo4j username")
    parser.add_argument("--neo4j-password", default="password", help="Neo4j password")
    
    args = parser.parse_args()
    xml_path = args.xml_path
    json_path = args.json_path
    skip_convert = args.skip_convert
    neo4j_uri = args.neo4j_uri
    neo4j_username = args.neo4j_username
    neo4j_password = args.neo4j_password

    # Step 1: Convert XML to JSON
    if not skip_convert:
        if os.path.exists(xml_path):
            print(f"[Step 1] Converting XML files from {xml_path} to {json_path}...")
            convert_xml_to_json(input_dir=xml_path, output_dir=json_path)
        else:
            print(f"[Step 1] Skipped: XML input directory '{xml_path}' not found.")

    # Step 2: Merge JSON into Neo4j
    print(f"[Step 2] Merging JSON data from {json_path} into Neo4j...")
    run_merge(json_path=json_path, neo4j_uri=neo4j_uri, neo4j_username=neo4j_username, neo4j_password=neo4j_password)
    
    # Step 3: Import AXL export
    print(f"[Step 3] Importing AXL export from {json_path}...")
    run_export_axl(input_dir=json_path, neo4j_uri=neo4j_uri, neo4j_username=neo4j_username, neo4j_password=neo4j_password)

if __name__ == "__main__":
    main()
