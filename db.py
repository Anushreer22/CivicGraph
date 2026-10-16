import os
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

# Load .env safely without printing secrets
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "1b19d07a")

_driver = None

def get_driver():
    global _driver
    if _driver is None:
        if not NEO4J_URI or not NEO4J_PASSWORD:
            raise ValueError("NEO4J_URI and NEO4J_PASSWORD must be configured in .env")
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver

def run(query: str, params: dict = None) -> list:
    """Executes a Cypher query using the configured NEO4J_DATABASE and returns results as plain dicts."""
    driver = get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(query, params or {})
        return [record.data() for record in result]

def run_single(query: str, params: dict = None) -> dict:
    """Executes a Cypher query and returns the first record as a plain dict, or None."""
    driver = get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        record = session.run(query, params or {}).single()
        return record.data() if record else None

def close_driver():
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None

