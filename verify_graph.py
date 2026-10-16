import db

def verify():
    print("=" * 80)
    print("PHASE A: VERIFYING GRAPH IN NEO4J AURA")
    print("=" * 80)

    # 1. Node counts per label
    labels = [
        "Ward", "IssueType", "Year", "Incident", "Complaint", 
        "Infrastructure", "TransferStation", "WasteProcessingPlant", "CollectionRoute",
        "Contractor", "Project", "WorkOrder"
    ]
    print("\n1. Node counts per label:")
    total_nodes = 0
    for lbl in labels:
        res = db.run_single(f"MATCH (n:`{lbl}`) RETURN count(n) AS cnt")
        cnt = res["cnt"] if res else 0
        print(f"  :{lbl:<22} = {cnt:,}")
        if lbl not in ["TransferStation", "WasteProcessingPlant", "CollectionRoute"]:
            total_nodes += cnt

    real_nodes = db.run_single("MATCH (n {source: 'real'}) RETURN count(n) AS cnt")["cnt"]
    syn_nodes = db.run_single("MATCH (n {source: 'synthetic'}) RETURN count(n) AS cnt")["cnt"]
    print(f"  Total Unique Nodes: {real_nodes + syn_nodes:,} (Real: {real_nodes:,}, Synthetic: {syn_nodes:,})")

    # Relationship counts per type
    rel_types = [
        "HAS_VOLUME", "IN_WARD", "FOR_ISSUE", "APPEARS_IN", 
        "DEPENDS_ON", "LOCATED_IN", "AFFECTS", "ASSIGNED_TO", "PART_OF", "MAY_CONTRIBUTE_TO"
    ]
    print("\nRelationship counts per type:")
    total_rels = 0
    for rt in rel_types:
        res = db.run_single(f"MATCH ()-[r:`{rt}`]->() RETURN count(r) AS cnt")
        cnt = res["cnt"] if res else 0
        total_rels += cnt
        print(f"  [:{rt:<18}] = {cnt:,}")

    real_rels = db.run_single("MATCH ()-[r {source: 'real'}]->() RETURN count(r) AS cnt")["cnt"]
    syn_rels = db.run_single("MATCH ()-[r {source: 'synthetic'}]->() RETURN count(r) AS cnt")["cnt"]
    print(f"  Total Relationships: {total_rels:,} (Real: {real_rels:,}, Synthetic: {syn_rels:,})")

    # 2. Story path check:
    # WorkOrder -[:AFFECTS]-> Infrastructure <-[:DEPENDS_ON*1..3]- Infrastructure
    print("\n" + "=" * 80)
    print("2. STORY PATH CHECK:")
    print("Cypher: MATCH (wo:WorkOrder)-[:AFFECTS]->(target:Infrastructure)<-[:DEPENDS_ON*1..3]-(source:Infrastructure)")
    print("=" * 80)

    story_query = """
        MATCH (wo:WorkOrder)-[:AFFECTS]->(target:Infrastructure)<-[:DEPENDS_ON*1..3]-(source:Infrastructure)
        OPTIONAL MATCH (target)-[:LOCATED_IN]->(tw:Ward)
        OPTIONAL MATCH (source)-[:LOCATED_IN]->(sw:Ward)
        RETURN wo.id AS work_order_id,
               wo.name AS work_order_name,
               wo.status AS status,
               target.name AS affected_infra,
               tw.name AS affected_infra_ward,
               source.name AS dependent_infra,
               sw.name AS dependent_infra_ward
        ORDER BY wo.id, dependent_infra
    """
    story_results = db.run(story_query)
    for r in story_results:
        print(f"  [{r['work_order_id']}] {r['work_order_name']} ({r['status']})")
        print(f"    |-- AFFECTS -> {r['affected_infra']} (in {r['affected_infra_ward']})")
        print(f"    |-- <-DEPENDS_ON- {r['dependent_infra']} (in {r['dependent_infra_ward']})\n")

    # 3. Top 5 incidents by complaint count
    print("=" * 80)
    print("3. TOP 5 INCIDENTS BY COMPLAINT COUNT:")
    print("=" * 80)

    top_inc_query = """
        MATCH (inc:Incident)
        MATCH (inc)-[:IN_WARD]->(w:Ward)
        MATCH (inc)-[:FOR_ISSUE]->(it:IssueType)
        RETURN inc.id AS incident_id,
               w.name AS ward,
               it.name AS issue_type,
               inc.complaint_count AS complaint_count,
               inc.open_count AS open_count,
               inc.resolved_count AS resolved_count,
               inc.status_note AS status_note
        ORDER BY inc.complaint_count DESC
        LIMIT 5
    """
    top_incidents = db.run(top_inc_query)
    thanisandra_swm_found = False
    for idx, inc in enumerate(top_incidents, 1):
        is_th_swm = (inc["ward"] == "Thanisandra" and inc["issue_type"] == "Solid Waste Management")
        if is_th_swm:
            thanisandra_swm_found = True
        marker = "[CONFIRMED]" if is_th_swm else ""
        print(f"  {idx}. {inc['incident_id']}: {inc['ward']} - {inc['issue_type']} | Complaints: {inc['complaint_count']} (Open: {inc['open_count']}, Resolved: {inc['resolved_count']}) {marker}")

    print(f"\nThanisandra / Solid Waste Management confirmed among top 5: {thanisandra_swm_found}")

if __name__ == '__main__':
    verify()
