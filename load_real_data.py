import csv
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

# Load environment variables safely without printing
load_dotenv()

URI = os.getenv("NEO4J_URI")
USERNAME = os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD")
DATABASE = os.getenv("NEO4J_DATABASE", "1b19d07a")

DATA_DIR = Path(r"c:\Users\ANUSHREE R\civicgraph\data")

def get_driver():
    if not URI or not PASSWORD:
        raise ValueError("NEO4J_URI and NEO4J_PASSWORD must be configured in .env")
    return GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD), max_connection_lifetime=3600, connection_timeout=60.0)

def run_cypher(session, query, params=None):
    if params:
        return session.run(query, params)
    return session.run(query)

def load_graph():
    print("=" * 80)
    print("LOADING REAL & SYNTHETIC DATA INTO NEO4J")
    print("=" * 80)

    driver = get_driver()
    
    with driver.session(database=DATABASE) as session:
        # 1. Clear existing database
        print("Clearing existing database...")
        session.run("MATCH (n) DETACH DELETE n")

        # 2. Create constraints
        print("Creating constraints...")
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (w:Ward) REQUIRE w.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (it:IssueType) REQUIRE it.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (y:Year) REQUIRE y.year IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (inc:Incident) REQUIRE inc.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Complaint) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (infra:Infrastructure) REQUIRE infra.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (wo:WorkOrder) REQUIRE wo.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (con:Contractor) REQUIRE con.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Project) REQUIRE p.name IS UNIQUE",
        ]
        for c in constraints:
            session.run(c)

        # 3. Load Wards
        print("Loading Wards...")
        wards = []
        with open(DATA_DIR / "clean_wards.csv", 'r', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                wards.append({'id': r['ward_id'], 'name': r['ward_name'], 'source': r['source']})
        session.run("""
            UNWIND $batch AS row
            CREATE (w:Ward:Location {id: row.id, name: row.name, source: row.source})
        """, {'batch': wards})
        print(f"Loaded {len(wards)} Ward nodes.")

        # 4. Load IssueTypes
        print("Loading IssueTypes...")
        issue_types = []
        with open(DATA_DIR / "clean_issue_types.csv", 'r', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                issue_types.append({'id': r['issue_id'], 'name': r['issue_name'], 'source': r['source']})
        session.run("""
            UNWIND $batch AS row
            CREATE (it:IssueType {id: row.id, name: row.name, source: row.source})
        """, {'batch': issue_types})
        print(f"Loaded {len(issue_types)} IssueType nodes.")

        # 5. Load Years
        print("Loading Years...")
        session.run("""
            CREATE (:Year {year: 2024, source: 'real'}),
                   (:Year {year: 2025, source: 'real'})
        """)

        # 6. Load Volumes (HAS_VOLUME relationships)
        print("Loading HAS_VOLUME relationships...")
        vols_2024 = []
        vols_2025 = []
        with open(DATA_DIR / "clean_volumes.csv", 'r', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                vols_2024.append({
                    'ward': r['ward_name'],
                    'issue': r['issue_type'],
                    'count': int(r['h1_2024_count']),
                    'full_year_count': int(r['full_year_2024_count']),
                    'period': 'H1 2024 (Jan 1-Jun 19)',
                    'source': 'real'
                })
                vols_2025.append({
                    'ward': r['ward_name'],
                    'issue': r['issue_type'],
                    'count': int(r['h1_2025_count']),
                    'pct_change': float(r['pct_change']),
                    'period': 'H1 2025 (Jan 1-Jun 19)',
                    'source': 'real'
                })

        session.run("""
            UNWIND $batch AS row
            MATCH (w:Ward {name: row.ward}), (it:IssueType {name: row.issue})
            CREATE (w)-[:HAS_VOLUME {
                year: 2024,
                count: row.count,
                full_year_count: row.full_year_count,
                period: row.period,
                issue: row.issue,
                source: row.source
            }]->(it)
        """, {'batch': vols_2024})

        session.run("""
            UNWIND $batch AS row
            MATCH (w:Ward {name: row.ward}), (it:IssueType {name: row.issue})
            CREATE (w)-[:HAS_VOLUME {
                year: 2025,
                count: row.count,
                pct_change: row.pct_change,
                period: row.period,
                issue: row.issue,
                source: row.source
            }]->(it)
        """, {'batch': vols_2025})
        print(f"Loaded {len(vols_2024) + len(vols_2025)} HAS_VOLUME relationships.")

        # 7. Load Incidents
        print("Loading Incidents...")
        incidents = []
        with open(DATA_DIR / "clean_incidents.csv", 'r', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                incidents.append({
                    'id': r['incident_id'],
                    'ward': r['ward'],
                    'issue_type': r['issue_type'],
                    'complaint_count': int(r['complaint_count']),
                    'open_count': int(r['open_count']),
                    'resolved_count': int(r['resolved_count']),
                    'baseline_weekly': float(r['baseline_weekly']),
                    'spike_multiplier': float(r['spike_multiplier']),
                    'spike_week': int(r['spike_week']),
                    'spike_complaints': int(r['spike_complaints']),
                    'status_note': r['status_note'],
                    'source': r['source']
                })

        session.run("""
            UNWIND $batch AS row
            MATCH (w:Ward {name: row.ward}), (it:IssueType {name: row.issue_type})
            CREATE (inc:Incident {
                id: row.id,
                ward: row.ward,
                issue_type: row.issue_type,
                complaint_count: row.complaint_count,
                open_count: row.open_count,
                resolved_count: row.resolved_count,
                baseline_weekly: row.baseline_weekly,
                spike_multiplier: row.spike_multiplier,
                spike_week: row.spike_week,
                spike_complaints: row.spike_complaints,
                status_note: row.status_note,
                source: row.source
            })
            CREATE (inc)-[:IN_WARD {source: 'real'}]->(w)
            CREATE (inc)-[:FOR_ISSUE {source: 'real'}]->(it)
        """, {'batch': incidents})
        print(f"Loaded {len(incidents)} Incident nodes.")

        # 8. Load Complaints in batches of 500
        print("Loading Complaints...")
        complaints = []
        with open(DATA_DIR / "clean_complaints.csv", 'r', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                complaints.append({
                    'id': r['complaint_id'],
                    'created_at': r['created_at'],
                    'ward': r['ward'],
                    'category': r['category'],
                    'sub_category': r['sub_category'],
                    'status': r['status'],
                    'issue_type': r['issue_type'],
                    'text': r['text'],
                    'language': r['language'],
                    'source': r['source'],
                    'text_source': r['text_source']
                })

        batch_size = 200
        for i in range(0, len(complaints), batch_size):
            batch = complaints[i:i + batch_size]
            session.run("""
                UNWIND $batch AS row
                MATCH (w:Ward {name: row.ward}), (it:IssueType {name: row.issue_type})
                CREATE (c:Complaint {
                    id: row.id,
                    created_at: row.created_at,
                    ward: row.ward,
                    category: row.category,
                    sub_category: row.sub_category,
                    status: row.status,
                    issue_type: row.issue_type,
                    text: row.text,
                    language: row.language,
                    source: row.source,
                    text_source: row.text_source
                })
                CREATE (c)-[:IN_WARD {source: 'real'}]->(w)
                CREATE (c)-[:FOR_ISSUE {source: 'real'}]->(it)
            """, {'batch': batch})
        print(f"Loaded {len(complaints)} Complaint nodes.")

        # 9. Link Complaints to Incidents (APPEARS_IN)
        print("Linking Complaints to Incidents (APPEARS_IN)...")
        links = []
        with open(DATA_DIR / "clean_complaint_incident_links.csv", 'r', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                links.append({'cid': r['complaint_id'], 'iid': r['incident_id'], 'source': r['source']})
        
        for i in range(0, len(links), batch_size):
            batch = links[i:i + batch_size]
            session.run("""
                UNWIND $batch AS row
                MATCH (c:Complaint {id: row.cid}), (inc:Incident {id: row.iid})
                CREATE (c)-[:APPEARS_IN {source: row.source}]->(inc)
            """, {'batch': batch})
        print(f"Loaded {len(links)} APPEARS_IN relationships.")

        # 10. Load Synthetic Dependency Layer
        print("Loading Synthetic Dependency Layer...")
        with open(DATA_DIR / "clean_synthetic_layer.json", 'r', encoding='utf-8') as f:
            syn_data = json.load(f)

        # Infrastructure
        for inf_item in syn_data['infrastructure']:
            session.run(f"""
                MATCH (w:Ward {{name: $ward}})
                CREATE (infra:Infrastructure:{inf_item['type']} {{
                    id: $id,
                    name: $name,
                    type: $type,
                    ward: $ward,
                    source: $source
                }})
                CREATE (infra)-[:LOCATED_IN {{source: 'synthetic'}}]->(w)
            """, inf_item)

        # Infra dependencies
        for dep in syn_data['infra_dependencies']:
            session.run("""
                MATCH (a:Infrastructure {id: $from_id}), (b:Infrastructure {id: $to_id})
                CREATE (a)-[:DEPENDS_ON {source: $source}]->(b)
            """, {'from_id': dep['from'], 'to_id': dep['to'], 'source': dep['source']})

        # Contractors
        session.run("""
            UNWIND $batch AS row
            CREATE (:Contractor {id: row.id, name: row.name, source: row.source})
        """, {'batch': syn_data['contractors']})

        # Projects
        session.run("""
            UNWIND $batch AS row
            CREATE (:Project {id: row.id, name: row.name, source: row.source})
        """, {'batch': syn_data['projects']})

        # Work Orders
        for wo in syn_data['work_orders']:
            session.run("""
                MATCH (infra:Infrastructure {id: $target_infra})
                MATCH (con:Contractor {id: $contractor})
                MATCH (p:Project {id: $project})
                MATCH (it:IssueType {name: $contributes_to})
                CREATE (w:WorkOrder {
                    id: $id,
                    name: $name,
                    status: $status,
                    delay_days: $delay_days,
                    contributes_to: $contributes_to,
                    source: $source
                })
                CREATE (w)-[:AFFECTS {source: 'synthetic'}]->(infra)
                CREATE (w)-[:ASSIGNED_TO {source: 'synthetic'}]->(con)
                CREATE (w)-[:PART_OF {source: 'synthetic'}]->(p)
                CREATE (w)-[:MAY_CONTRIBUTE_TO {source: 'synthetic'}]->(it)
            """, wo)
        print("Loaded synthetic layer (Infrastructure, Contractors, Projects, WorkOrders).")

        # 11. Verification Query: Print final node and relationship counts
        print("\n" + "=" * 80)
        print("GRAPH VERIFICATION: FINAL COUNTS PER LABEL AND RELATIONSHIP TYPE")
        print("=" * 80)

        node_counts = session.run("""
            CALL db.labels() YIELD label
            CALL apoc.cypher.run('MATCH (n:`' + label + '`) RETURN count(n) AS cnt', {}) YIELD value
            RETURN label, value.cnt AS count
            ORDER BY count DESC
        """).data() if False else None # Avoid apoc dependency if apoc not available

        # Safe count per label without APOC:
        labels_to_check = ['Ward', 'IssueType', 'Year', 'Incident', 'Complaint', 'Infrastructure', 'TransferStation', 'WasteProcessingPlant', 'CollectionRoute', 'Contractor', 'Project', 'WorkOrder']
        print("\n--- Node Counts by Label ---")
        total_nodes = 0
        for lbl in labels_to_check:
            res = session.run(f"MATCH (n:`{lbl}`) RETURN count(n) AS cnt").single()
            cnt = res['cnt']
            print(f"  :{lbl:<22} = {cnt:,}")
            if lbl not in ['TransferStation', 'WasteProcessingPlant', 'CollectionRoute']:
                total_nodes += cnt
        
        # Real vs Synthetic nodes
        real_nodes = session.run("MATCH (n {source: 'real'}) RETURN count(n) AS cnt").single()['cnt']
        syn_nodes = session.run("MATCH (n {source: 'synthetic'}) RETURN count(n) AS cnt").single()['cnt']
        print(f"\n  Total Unique Nodes in Graph: {real_nodes + syn_nodes:,} (Real: {real_nodes:,}, Synthetic: {syn_nodes:,})")

        # Relationship counts
        print("\n--- Relationship Counts by Type ---")
        rel_types = ['HAS_VOLUME', 'IN_WARD', 'FOR_ISSUE', 'APPEARS_IN', 'DEPENDS_ON', 'LOCATED_IN', 'AFFECTS', 'ASSIGNED_TO', 'PART_OF', 'MAY_CONTRIBUTE_TO']
        total_rels = 0
        for rt in rel_types:
            res = session.run(f"MATCH ()-[r:`{rt}`]->() RETURN count(r) AS cnt").single()
            cnt = res['cnt']
            total_rels += cnt
            print(f"  [:{rt:<18}] = {cnt:,}")

        real_rels = session.run("MATCH ()-[r {source: 'real'}]->() RETURN count(r) AS cnt").single()['cnt']
        syn_rels = session.run("MATCH ()-[r {source: 'synthetic'}]->() RETURN count(r) AS cnt").single()['cnt']
        print(f"\n  Total Relationships in Graph: {total_rels:,} (Real: {real_rels:,}, Synthetic: {syn_rels:,})")

    driver.close()
    print("\nNeo4j graph loading completed successfully!")

if __name__ == '__main__':
    load_graph()

