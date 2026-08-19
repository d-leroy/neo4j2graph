import os
import sys
from neo4j import GraphDatabase

def main(address):
    URI = f"bolt://{address}:7687"
    AUTH = ("neo4j", "password")

    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        driver.verify_connectivity()

if __name__ == "__main__":
    args = sys.argv
    if len(args) == 1: main('localhost')
    else:
        main(args[1])

