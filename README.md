# panoramix

A set of utilities for running Arcane sequentially, converting its outputs, and loading results into a Neo4j graph database.

## Running Arcane sequentially
Use the following Arcane options when you need a non‑interactive/export run:
```
-A,export_format=xml,export_output_directory=[path],export_only=true
```
> The `export_only` option causes Arcane to terminate before the simulation starts by raising an error. This is intentional and expected. The error simply stops execution once the XML export is complete.


## Converting extracted XML configs to JSON
```
panoramix
```

**Note:** The `panoramix` CLI now handles both XML-to-JSON conversion and database import in a single command. It automatically:
1. Converts XML files from `./xml` to JSON in `./arc_json`
2. Merges the JSON data into Neo4j
3. Imports AXL export files into Neo4j

## Installation & Setup
The easiest way to get started is to install the published package from PyPI:

```bash
pip install panoramix
```

Optionally create a virtual environment for development or isolation:

```bash
python -m venv .venv
# activate the environment:
source .venv/bin/activate        # macOS/Linux
.\.venv\Scripts\activate      # Windows
pip install panoramix         # or `pip install -e .` when working on the code
```

Once installed, the `panoramix` command is available on your PATH:

```bash
panoramix --help
panoramix --xml-path ./xml --json-path ./arc_json --neo4j-password password
```

For a one‑off invocation without activating the env, call the binary directly:

```bash
./.venv/bin/panoramix --xml-path ./xml          # Linux/macOS
.\.venv\Scripts\panoramix --xml-path .\xml   # Windows
```

---

## Converting .axl to JSON via axlstar
```
axl2ccT4 -l json -o \[output_path\] \[path_to_axl\]/Mahyco.axl
```

## Docker deployment
```
docker run -d -p 7474:7474 -p 7687:7687 -v $PWD/data:/data:Z -v $PWD/plugins:/plugins:Z --name neo4j-test -e NEO4J_apoc_export_file_enabled=true -e NEO4J_apoc_import_file_enabled=true -e NEO4J_apoc_import_file_use__neo4j__config=true -e NEO4J_PLUGINS=\[\"apoc\",\"apoc-extended\"\] -e NEO4J_AUTH=neo4j/password neo4j:latest
```

## Populating the database

Run **`panoramix`**; the CLI performs all three steps in one execution:
1. Convert XML files to JSON
2. Merge the JSON data into Neo4j
3. Import any AXL export files into Neo4j

One run is sufficient.

### CLI options
```
panoramix [OPTIONS]

Options:
  --xml-path PATH               Path to XML input directory (default: ./xml)
  --json-path PATH              Path to JSON directory - output of conversion and input for merge (default: ./arc_json)
  --skip-convert                Skip XML to JSON conversion step (default: false)
  --neo4j-uri URI               Neo4j connection URI (default: bolt://localhost:7687)
  --neo4j-username USERNAME     Neo4j username (default: neo4j)
  --neo4j-password PASSWORD     Neo4j password (default: password)
```

### Examples
```bash
panoramix --xml-path ./config/xml --json-path ./config/json --neo4j-uri bolt://localhost:7687 --neo4j-username neo4j --neo4j-password password
```

## Interface web
```
http://localhost:7474/browser/
```

## Sample specification query for a named option
```
MATCH p=(o: Option {fullName: "Mahyco/boundary-condition"})-[r:SPECIFIES]->()
return p
```

## Coverage of all options
```
MATCH (o)-[:SPECIFIES]->(n)
WITH apoc.map.clean(properties(n), ['uid'], []) AS props, coalesce(o.fullName, o.name) AS name
UNWIND keys(props) AS key
RETURN name, key, props[key] AS value, count(*) AS count
ORDER BY name, count DESC;
```