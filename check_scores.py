import db
import queries

incs = db.run('MATCH (inc:Incident) RETURN inc.id, inc.ward, inc.issue_type, inc.complaint_count ORDER BY inc.complaint_count DESC LIMIT 10')
for i in incs:
    ev = queries.evidence_for_incident(i['inc.id'])
    print(f"{i['inc.id']}: {i['inc.ward']} - {i['inc.issue_type']} (count={i['inc.complaint_count']})")
    print(f"   {ev['evidence_score_display']}")
    fired = [f"{r['rule']} (+{r['points']}, {r['category']})" for r in ev['rules_fired']]
    print("   Rules fired:", ", ".join(fired))
    print()
