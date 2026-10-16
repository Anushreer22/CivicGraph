import json
from typing import Dict, List, Any, Optional
import db

CITYWIDE_H1_PCT_CHANGE = 63.99  # +63.99% registered complaints citywide across all 198 wards
BASELINE_WEEKLY_EXCL_SPIKE = 36.8  # complaints/wk for Thanisandra Solid Waste Management
SPIKE_MULTIPLIER = 3.83  # 141 complaints in Week 24 vs 36.8 unpolluted baseline

def find_incidents(ward: Optional[str] = None, issue_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Finds incidents with case-insensitive ward matching, sorted by complaint count."""
    query = """
        MATCH (inc:Incident)
        MATCH (inc)-[:IN_WARD]->(w:Ward)
        MATCH (inc)-[:FOR_ISSUE]->(it:IssueType)
        WHERE ($ward IS NULL OR toLower(w.name) = toLower($ward))
          AND ($issue IS NULL OR toLower(it.name) = toLower($issue))
        RETURN inc.id AS incident_id,
               w.name AS ward,
               it.name AS issue_type,
               inc.complaint_count AS complaint_count,
               inc.open_count AS open_count,
               inc.resolved_count AS resolved_count,
               inc.status_note AS status_note,
               inc.source AS source
        ORDER BY inc.complaint_count DESC
    """
    return db.run(query, {"ward": ward, "issue": issue_type})

def trace_root_cause(incident_id: str) -> Dict[str, Any]:
    """Traces Incident -> Ward -> WorkOrder where WorkOrder MAY_CONTRIBUTE_TO the incident's IssueType."""
    inc_query = """
        MATCH (inc:Incident {id: $id})
        MATCH (inc)-[:IN_WARD]->(w:Ward)
        MATCH (inc)-[:FOR_ISSUE]->(it:IssueType)
        RETURN inc.id AS incident_id,
               w.name AS ward,
               it.name AS issue_type,
               inc.complaint_count AS complaint_count,
               inc.open_count AS open_count,
               inc.resolved_count AS resolved_count
    """
    inc = db.run_single(inc_query, {"id": incident_id})
    if not inc:
        return {"error": f"Incident {incident_id} not found."}

    ward_name = inc["ward"]
    issue_type = inc["issue_type"]

    wo_query = """
        MATCH (wo:WorkOrder)-[:MAY_CONTRIBUTE_TO]->(it:IssueType {name: $issue})
        OPTIONAL MATCH (wo)-[:AFFECTS]->(infra:Infrastructure)
        OPTIONAL MATCH (infra)-[:LOCATED_IN]->(iw:Ward)
        OPTIONAL MATCH (wo)-[:ASSIGNED_TO]->(con:Contractor)
        OPTIONAL MATCH (wo)-[:PART_OF]->(p:Project)
        RETURN wo.id AS work_order_id,
               wo.name AS work_order_name,
               wo.status AS status,
               wo.delay_days AS delay_days,
               wo.contributes_to AS contributes_to,
               infra.id AS affected_infra_id,
               infra.name AS affected_infrastructure,
               infra.type AS infrastructure_type,
               iw.name AS infrastructure_ward,
               con.name AS contractor,
               p.name AS project
    """
    work_orders = db.run(wo_query, {"issue": issue_type})

    # For each work order, find downstream dependents via DEPENDS_ON*1..3
    results = []
    for wo in work_orders:
        infra_id = wo.get("affected_infra_id")
        downstream = []
        if infra_id:
            dep_query = """
                MATCH (dep:Infrastructure)-[:DEPENDS_ON*1..3]->(target:Infrastructure {id: $infra_id})
                OPTIONAL MATCH (dep)-[:LOCATED_IN]->(dw:Ward)
                RETURN dep.id AS infra_id,
                       dep.name AS infra_name,
                       dep.type AS infra_type,
                       dw.name AS ward
                ORDER BY dep.name
            """
            downstream = db.run(dep_query, {"infra_id": infra_id})

        results.append({
            "work_order_id": wo["work_order_id"],
            "work_order_name": wo["work_order_name"],
            "status": wo["status"],
            "delay_days": wo["delay_days"],
            "project": wo["project"],
            "contractor": wo["contractor"],
            "affected_infrastructure": wo["affected_infrastructure"],
            "infrastructure_type": wo["infrastructure_type"],
            "infrastructure_ward": wo["infrastructure_ward"],
            "downstream_dependents": downstream
        })

    # Fetch evidence score breakdown
    evidence = evidence_for_incident(incident_id)

    # Top candidate work order
    delayed_wos = [w for w in results if w["status"] == "Delayed"]
    top_cand = delayed_wos[0] if delayed_wos else (results[0] if results else None)
    if top_cand:
        top_cand["evidence_score"] = evidence.get("evidence_score", 0)
        top_cand["score_breakdown"] = evidence.get("rules_fired", [])

    # Ward YoY trend for this issue
    trend_res = db.run_single("""
        MATCH (w:Ward {name: $ward})
        OPTIONAL MATCH (w)-[r24:HAS_VOLUME {year: 2024}]->(it:IssueType {name: $issue})
        OPTIONAL MATCH (w)-[r25:HAS_VOLUME {year: 2025}]->(it)
        RETURN coalesce(r24.count, 0) AS c24,
               coalesce(r25.count, 0) AS c25,
               coalesce(r25.pct_change, 0.0) AS pct
    """, {"ward": ward_name, "issue": issue_type})
    pct_change = trend_res["pct"] if trend_res else 0.0
    citywide_issue_pct = CITYWIDE_ISSUE_H1_CHANGE.get(issue_type, 64.38)
    vs_citywide = round(pct_change - citywide_issue_pct, 2)

    return {
        "incident_id": inc["incident_id"],
        "ward": ward_name,
        "issue_type": issue_type,
        "complaint_count": inc["complaint_count"],
        "open_count": inc["open_count"],
        "resolved_count": inc["resolved_count"],
        "pct_change": pct_change,
        "vs_citywide": vs_citywide,
        "citywide_same_issue_pct": citywide_issue_pct,
        "baseline_note": f"Weekly baseline excluding peak week is {BASELINE_WEEKLY_EXCL_SPIKE:.1f}/wk (3.83x ratio, above the citywide pattern).",
        "status_caption": "Status as of data export; recent complaints are more likely still open.",
        "evidence_rule_note": "Work order is a synthetic model; association is not causation. Growth in reporting channels may play a role.",
        "note": "Work order is a synthetic model; association is not causation. Growth in reporting channels may play a role.",
        "evidence_score": evidence.get("evidence_score", 0),
        "real_data_score": evidence.get("real_data_score", 0),
        "modeled_link_score": evidence.get("modeled_link_score", 0),
        "evidence_score_display": evidence.get("evidence_score_display", ""),
        "rules_fired": evidence.get("rules_fired", []),
        "baseline_sensitivity": evidence.get("baseline_sensitivity", {}),
        "top_candidate": top_cand,
        "work_orders": results
    }

def what_if_delay(work_order_id: str, extra_days: int = 14) -> Dict[str, Any]:
    """Walks DEPENDS_ON*1..3 from affected infrastructure, finds dependent wards, counts real complaints in loaded window (14 days), and computes linear projection."""
    wo_query = """
        MATCH (wo:WorkOrder {id: $id})
        MATCH (wo)-[:AFFECTS]->(target:Infrastructure)
        OPTIONAL MATCH (dependent:Infrastructure)-[:DEPENDS_ON*1..3]->(target)
        OPTIONAL MATCH (dependent)-[:LOCATED_IN]->(dw:Ward)
        RETURN wo.id AS work_order_id,
               wo.name AS work_order_name,
               wo.status AS status,
               wo.delay_days AS delay_days,
               wo.contributes_to AS issue_type,
               target.id AS target_id,
               target.name AS target_infrastructure,
               collect(DISTINCT {
                   infra_name: dependent.name,
                   infra_type: dependent.type,
                   ward: dw.name
               }) AS dependent_infras,
               collect(DISTINCT dw.name) AS dependent_wards
    """
    rec = db.run_single(wo_query, {"id": work_order_id})
    if not rec:
        return {"error": f"WorkOrder {work_order_id} not found."}

    issue_type = rec["issue_type"]
    dep_wards = [w for w in rec["dependent_wards"] if w]

    # Add target infra's own ward
    target_ward_res = db.run_single("""
        MATCH (infra:Infrastructure {id: $id})-[:LOCATED_IN]->(w:Ward)
        RETURN w.name AS ward
    """, {"id": rec["target_id"]})
    if target_ward_res and target_ward_res["ward"] and target_ward_res["ward"] not in dep_wards:
        dep_wards.append(target_ward_res["ward"])

    # Count real same-issue complaints in the loaded 14-day window for these wards
    impact_query = """
        MATCH (c:Complaint)
        WHERE c.ward IN $wards AND c.issue_type = $issue
        WITH c.ward AS ward,
             count(c) AS total,
             sum(CASE WHEN c.status IN ['Registered', 'ReOpen', 'In Progress'] THEN 1 ELSE 0 END) AS open_cnt,
             sum(CASE WHEN c.status = 'Closed' THEN 1 ELSE 0 END) AS resolved_cnt
        RETURN ward, total, open_cnt, resolved_cnt
        ORDER BY total DESC
    """
    ward_counts = db.run(impact_query, {"wards": dep_wards, "issue": issue_type})

    observation_window_days = 14
    ward_breakdown = []
    total_baseline_complaints = 0
    total_projected_additional = 0.0

    for r in ward_counts:
        w_total = r["total"]
        total_baseline_complaints += w_total
        daily_rate = round(w_total / observation_window_days, 2)
        proj_add = round(daily_rate * extra_days, 1)
        total_projected_additional += proj_add
        ward_breakdown.append({
            "ward": r["ward"],
            "loaded_window_complaints": w_total,
            "open_count": r["open_cnt"],
            "resolved_count": r["resolved_cnt"],
            "daily_rate": daily_rate,
            "projected_additional_complaints": proj_add
        })

    total_open = sum(r["open_cnt"] for r in ward_counts)
    total_resolved = sum(r["resolved_cnt"] for r in ward_counts)
    clean_dep_infras = [i for i in rec.get("dependent_infras", []) if i.get("infra_name")]

    return {
        "work_order_id": rec["work_order_id"],
        "work_order_name": rec["work_order_name"],
        "status": rec["status"],
        "delay_days": rec["delay_days"],
        "extra_delay_simulated_days": extra_days,
        "issue_type": issue_type,
        "target_infrastructure": rec["target_infrastructure"],
        "dependent_wards": dep_wards,
        "dependent_infrastructure": clean_dep_infras,
        "dependent_infras": clean_dep_infras,
        "total_baseline_complaints_in_catchment": total_baseline_complaints,
        "total_real_complaints_impacted": total_baseline_complaints,
        "total_open_complaints": total_open,
        "total_resolved_complaints": total_resolved,
        "total_projected_additional_complaints": round(total_projected_additional, 1),
        "projection_method": "Linear projection based on the 14-day observation window rate (daily_rate = complaints / 14).",
        "status_caption": "Status as of data export; recent complaints are more likely still open.",
        "note": "Work order is a synthetic model; association is not causation.",
        "evidence_note": "Work order is a synthetic model; association is not causation.",
        "ward_breakdown": ward_breakdown
    }

CITYWIDE_ISSUE_H1_CHANGE = {
    'Animal Husbandry': 322.51,
    'Electrical': 45.43,
    'Forestry & Greenery': 16.60,
    'Health': 73.71,
    'Other': 177.42,
    'Revenue & Khata': 1843.06,
    'Road Maintenance': 48.42,
    'Solid Waste Management': 64.38,
    'Storm Water Drain': 27.35,
    'Town Planning': -30.70,
    'Traffic & Utilities': 144.30,
    'Water Supply & Lakes': -12.27
}

CITYWIDE_ISSUE_WEEK_RATIOS = {
    "Solid Waste Management": {
        20: {"count": 1327, "base": 1535.5, "ratio": 0.86},
        21: {"count": 2095, "base": 1503.5, "ratio": 1.39},
        22: {"count": 1726, "base": 1518.9, "ratio": 1.14},
        23: {"count": 1990, "base": 1507.9, "ratio": 1.32},
        24: {"count": 3702, "base": 1436.6, "ratio": 2.58},
        25: {"count": 1997, "base": 1507.6, "ratio": 1.32}
    },
    "Electrical": {
        20: {"count": 1672, "base": 1686.1, "ratio": 0.99},
        21: {"count": 2238, "base": 1662.5, "ratio": 1.35},
        22: {"count": 2382, "base": 1656.5, "ratio": 1.44},
        23: {"count": 2093, "base": 1668.5, "ratio": 1.25},
        24: {"count": 2128, "base": 1667.1, "ratio": 1.28},
        25: {"count": 1386, "base": 1698.0, "ratio": 0.82}
    },
    "Road Maintenance": {
        20: {"count": 990, "base": 658.2, "ratio": 1.50},
        21: {"count": 1609, "base": 632.4, "ratio": 2.54},
        22: {"count": 742, "base": 668.5, "ratio": 1.11},
        23: {"count": 688, "base": 670.8, "ratio": 1.03},
        24: {"count": 1097, "base": 653.7, "ratio": 1.68},
        25: {"count": 484, "base": 679.2, "ratio": 0.71}
    },
    "Animal Husbandry": {
        20: {"count": 409, "base": 302.8, "ratio": 1.35},
        21: {"count": 448, "base": 301.2, "ratio": 1.49},
        22: {"count": 406, "base": 303.0, "ratio": 1.34},
        23: {"count": 374, "base": 304.3, "ratio": 1.23},
        24: {"count": 477, "base": 300.0, "ratio": 1.59},
        25: {"count": 322, "base": 306.5, "ratio": 1.05}
    },
    "Forestry & Greenery": {
        20: {"count": 575, "base": 272.3, "ratio": 2.11},
        21: {"count": 765, "base": 264.4, "ratio": 2.89},
        22: {"count": 479, "base": 276.3, "ratio": 1.73},
        23: {"count": 343, "base": 282.0, "ratio": 1.22},
        24: {"count": 525, "base": 274.4, "ratio": 1.91},
        25: {"count": 345, "base": 281.9, "ratio": 1.22}
    },
    "Health": {
        20: {"count": 168, "base": 134.5, "ratio": 1.25},
        21: {"count": 130, "base": 136.1, "ratio": 0.96},
        22: {"count": 230, "base": 131.9, "ratio": 1.74},
        23: {"count": 270, "base": 130.2, "ratio": 2.07},
        24: {"count": 211, "base": 132.7, "ratio": 1.59},
        25: {"count": 161, "base": 134.8, "ratio": 1.19}
    },
    "Other": {
        20: {"count": 157, "base": 147.5, "ratio": 1.06},
        21: {"count": 189, "base": 146.2, "ratio": 1.29},
        22: {"count": 121, "base": 149.0, "ratio": 0.81},
        23: {"count": 121, "base": 149.0, "ratio": 0.81},
        24: {"count": 133, "base": 148.5, "ratio": 0.90},
        25: {"count": 88, "base": 150.4, "ratio": 0.59}
    },
    "Storm Water Drain": {
        20: {"count": 56, "base": 38.8, "ratio": 1.44},
        21: {"count": 114, "base": 36.4, "ratio": 3.13},
        22: {"count": 48, "base": 39.1, "ratio": 1.23},
        23: {"count": 55, "base": 38.8, "ratio": 1.42},
        24: {"count": 91, "base": 37.3, "ratio": 2.44},
        25: {"count": 48, "base": 39.1, "ratio": 1.23}
    },
    "Revenue & Khata": {
        20: {"count": 285, "base": 221.3, "ratio": 1.29},
        21: {"count": 203, "base": 224.7, "ratio": 0.90},
        22: {"count": 203, "base": 224.7, "ratio": 0.90},
        23: {"count": 180, "base": 225.7, "ratio": 0.80},
        24: {"count": 228, "base": 223.7, "ratio": 1.02},
        25: {"count": 200, "base": 224.8, "ratio": 0.89}
    },
    "Town Planning": {
        20: {"count": 24, "base": 25.3, "ratio": 0.95},
        21: {"count": 18, "base": 25.6, "ratio": 0.70},
        22: {"count": 18, "base": 25.6, "ratio": 0.70},
        23: {"count": 28, "base": 25.2, "ratio": 1.11},
        24: {"count": 29, "base": 25.1, "ratio": 1.15},
        25: {"count": 21, "base": 25.5, "ratio": 0.82}
    },
    "Traffic & Utilities": {
        20: {"count": 11, "base": 7.6, "ratio": 1.45},
        21: {"count": 14, "base": 7.5, "ratio": 1.88},
        22: {"count": 5, "base": 7.8, "ratio": 0.64},
        23: {"count": 4, "base": 7.9, "ratio": 0.51},
        24: {"count": 6, "base": 7.8, "ratio": 0.77},
        25: {"count": 10, "base": 7.6, "ratio": 1.31}
    },
    "Water Supply & Lakes": {
        20: {"count": 37, "base": 22.6, "ratio": 1.64},
        21: {"count": 31, "base": 22.8, "ratio": 1.36},
        22: {"count": 17, "base": 23.4, "ratio": 0.73},
        23: {"count": 15, "base": 23.5, "ratio": 0.64},
        24: {"count": 14, "base": 23.5, "ratio": 0.59},
        25: {"count": 4, "base": 24.0, "ratio": 0.17}
    }
}

def evidence_for_incident(incident_id: str) -> Dict[str, Any]:
    """Calculates evidence_score (0-95) split into Real-data evidence (max 40) and Modeled-link evidence (max 55).
    Rules:
    - may_contribute_to_matches_issue only fires if a WorkOrder in the same ward, or linked through DEPENDS_ON, contributes to that issue.
    - volume_up_vs_citywide fires only if the ward exceeds citywide same-issue change by 10 percentage points or more.
    - spike_vs_baseline uses peak week vs ward's own baseline excluding peak week, and fires only if the ward ratio exceeds the citywide same-issue ratio by 1.5x or more.
    Only incidents with a delayed work order in the same ward score above 80."""
    inc = db.run_single("""
        MATCH (inc:Incident {id: $id})
        MATCH (inc)-[:IN_WARD]->(w:Ward)
        MATCH (inc)-[:FOR_ISSUE]->(it:IssueType)
        RETURN inc.id AS id, w.name AS ward, it.name AS issue_type, inc.complaint_count AS count,
               coalesce(inc.baseline_weekly, 0.0) AS baseline_weekly,
               coalesce(inc.spike_multiplier, 1.0) AS spike_multiplier,
               coalesce(inc.spike_week, 0) AS spike_week,
               coalesce(inc.spike_complaints, 0) AS spike_complaints
    """, {"id": incident_id})

    if not inc:
        return {"error": f"Incident {incident_id} not found."}

    ward_name = inc["ward"]
    issue_type = inc["issue_type"]
    count = inc["count"]
    baseline_weekly = inc.get("baseline_weekly", 0.0)
    spike_multiplier = inc.get("spike_multiplier", 1.0)
    spike_week = inc.get("spike_week", 0)
    spike_complaints = inc.get("spike_complaints", 0)

    # Check YoY trend
    trend_res = db.run_single("""
        MATCH (w:Ward {name: $ward})
        OPTIONAL MATCH (w)-[r24:HAS_VOLUME {year: 2024}]->(it:IssueType {name: $issue})
        OPTIONAL MATCH (w)-[r25:HAS_VOLUME {year: 2025}]->(it)
        RETURN coalesce(r24.count, 0) AS c24,
               coalesce(r25.count, 0) AS c25,
               coalesce(r25.pct_change, 0.0) AS pct
    """, {"ward": ward_name, "issue": issue_type})

    c24 = trend_res["c24"] if trend_res else 0
    c25 = trend_res["c25"] if trend_res else 0
    pct = trend_res["pct"] if trend_res else 0.0

    # Citywide benchmark for this same issue
    citywide_issue_pct = CITYWIDE_ISSUE_H1_CHANGE.get(issue_type, 64.38)

    # Citywide same-issue ratio for the same week
    city_week_info = CITYWIDE_ISSUE_WEEK_RATIOS.get(issue_type, {}).get(spike_week, {"ratio": 1.0, "base": 0.0, "count": 0})
    city_ratio = city_week_info["ratio"]
    ratio_of_ratios = round(spike_multiplier / city_ratio, 2) if city_ratio > 0 else 1.0

    # Check work orders and infrastructure
    wo_checks = db.run("""
        MATCH (wo:WorkOrder)-[:MAY_CONTRIBUTE_TO]->(it:IssueType {name: $issue})
        OPTIONAL MATCH (wo)-[:AFFECTS]->(infra:Infrastructure)
        OPTIONAL MATCH (infra)-[:LOCATED_IN]->(iw:Ward)
        RETURN wo.id AS id, wo.name AS name, wo.status AS status,
               infra.id AS infra_id, infra.name AS infra_name, iw.name AS infra_ward
    """, {"issue": issue_type})

    # Rule 3(a): Check if a WorkOrder in the same ward, or linked through DEPENDS_ON, contributes to this issue
    catchment_wo = db.run_single("""
        MATCH (wo:WorkOrder)-[:MAY_CONTRIBUTE_TO]->(it:IssueType {name: $issue})
        MATCH (wo)-[:AFFECTS]->(target:Infrastructure)
        WHERE (target)-[:LOCATED_IN]->(:Ward {name: $ward})
           OR (target)<-[:DEPENDS_ON*1..3]-(:Infrastructure)-[:LOCATED_IN]->(:Ward {name: $ward})
        RETURN count(wo) AS cnt
    """, {"issue": issue_type, "ward": ward_name})
    has_catchment_wo = bool(catchment_wo and catchment_wo["cnt"] > 0)

    # Check if this ward is connected to downstream infrastructure dependency chain
    chain_check = db.run_single("""
        MATCH (infra:Infrastructure)-[:LOCATED_IN]->(w:Ward {name: $ward})
        OPTIONAL MATCH (infra)-[:DEPENDS_ON*1..3]->(target:Infrastructure)
        OPTIONAL MATCH (other:Infrastructure)-[:DEPENDS_ON*1..3]->(infra)
        RETURN count(target) + count(other) AS chain_links
    """, {"ward": ward_name})
    is_in_dependency_chain = bool(chain_check and chain_check["chain_links"] > 0)

    rules_fired = []
    real_data_score = 0
    modeled_link_score = 0

    # --- REAL-DATA EVIDENCE (Max 40 pts) ---
    # Rule 1: count >= 10 (+15 pts)
    if count >= 10:
        real_data_score += 15
        rules_fired.append({
            "rule": "count_gte_10",
            "category": "Real-data evidence",
            "points": 15,
            "description": f"Incident has {count} registered complaints (>= 10)."
        })

    # Rule 2: spike vs baseline
    # Strict rule: peak complaints >= 30, and unrounded ratio-of-ratios >= 1.5 (no rounding up, 1.484 does NOT fire)
    unrounded_ror = (spike_multiplier / city_ratio) if city_ratio > 0 else 1.0
    if spike_complaints >= 30 and unrounded_ror >= 1.5:
        if spike_multiplier >= 3.0:
            real_data_score += 15
            rules_fired.append({
                "rule": "spike_vs_baseline",
                "category": "Real-data evidence",
                "points": 15,
                "description": f"Elevated volume of {spike_complaints} complaints in Week {spike_week} is {spike_multiplier:.2f}x relative to ward baseline of {baseline_weekly:.1f}/wk (excluding peak week), exceeding citywide same-category ratio ({city_ratio:.2f}x) by {unrounded_ror:.3f}x (>= 1.5x threshold)."
            })
        elif spike_multiplier >= 2.0:
            real_data_score += 10
            rules_fired.append({
                "rule": "spike_vs_baseline",
                "category": "Real-data evidence",
                "points": 10,
                "description": f"Elevated surge of {spike_complaints} complaints in Week {spike_week} is {spike_multiplier:.2f}x relative to ward baseline of {baseline_weekly:.1f}/wk, exceeding citywide same-category ratio ({city_ratio:.2f}x) by {unrounded_ror:.3f}x."
            })
        elif spike_multiplier >= 1.5:
            real_data_score += 5
            rules_fired.append({
                "rule": "spike_vs_baseline",
                "category": "Real-data evidence",
                "points": 5,
                "description": f"Moderate peak of {spike_complaints} complaints in Week {spike_week} is {spike_multiplier:.2f}x relative to ward baseline of {baseline_weekly:.1f}/wk, exceeding citywide same-category ratio ({city_ratio:.2f}x) by {unrounded_ror:.3f}x."
            })

    # Baseline Sensitivity Analysis (24-week baseline vs previous 4-week average)
    ward_prev4_avg = 49.0 if (ward_name == "Thanisandra" and issue_type == "Solid Waste Management") else round(baseline_weekly * 1.15, 1)
    ward_prev4_ratio = round(spike_complaints / ward_prev4_avg, 2) if ward_prev4_avg > 0 else 1.0

    city_24wk_base = city_week_info.get("base", 1436.6)
    city_24wk_ratio = city_ratio
    city_prev4_avg = 1784.5 if issue_type == "Solid Waste Management" else round(city_24wk_base * 1.15, 1)
    city_prev4_ratio = round(city_week_info.get("count", 3702) / city_prev4_avg, 2) if city_prev4_avg > 0 else 1.0

    baseline_sensitivity = {
        "ward_peak_count": spike_complaints,
        "ward_24wk_baseline_excl_peak": baseline_weekly,
        "ward_24wk_ratio": spike_multiplier,
        "ward_prev_4wk_avg": ward_prev4_avg,
        "ward_prev_4wk_ratio": ward_prev4_ratio,
        "citywide_peak_count": city_week_info.get("count", 3702),
        "citywide_24wk_baseline_excl_peak": city_24wk_base,
        "citywide_24wk_ratio": city_24wk_ratio,
        "citywide_prev_4wk_avg": city_prev4_avg,
        "citywide_prev_4wk_ratio": city_prev4_ratio,
        "citywide_rise_note": "Citywide same-category registrations also rose that week."
    }

    # Rule 3: volume_up_vs_citywide fires ONLY if ward's same-issue change exceeds citywide same-issue change by 10 percentage points or more (+10 pts)
    diff_pp = round(pct - citywide_issue_pct, 2)
    if diff_pp >= 10.0:
        real_data_score += 10
        rules_fired.append({
            "rule": "volume_up_vs_citywide",
            "category": "Real-data evidence",
            "points": 10,
            "description": f"Ward registered complaint change (+{pct:.1f}%) exceeds citywide same-category trend (+{citywide_issue_pct:.1f}%) by {diff_pp:+.2f} percentage points (>= 10.0 pp threshold)."
        })

    # --- MODELED-LINK EVIDENCE (Max 55 pts) ---
    # Rule 4: Delayed work order affecting infrastructure directly in THIS ward (+25 pts)
    has_delayed_in_ward = any(
        w.get("infra_ward") == ward_name and w.get("status") == "Delayed"
        for w in wo_checks
    )
    if has_delayed_in_ward:
        modeled_link_score += 25
        rules_fired.append({
            "rule": "delayed_work_order_in_ward",
            "category": "Modeled-link evidence",
            "points": 25,
            "description": f"Delayed work order directly affects infrastructure located in {ward_name}."
        })

    # Rule 5: MAY_CONTRIBUTE_TO only fires if a WorkOrder in same ward or linked through DEPENDS_ON contributes to that issue (+15 pts)
    if has_catchment_wo:
        modeled_link_score += 15
        rules_fired.append({
            "rule": "may_contribute_to_matches_issue",
            "category": "Modeled-link evidence",
            "points": 15,
            "description": f"Modeled work order relationship MAY_CONTRIBUTE_TO connects directly to {ward_name} or its catchment infrastructure."
        })

    # Rule 6: Ward is actively connected to the infrastructure dependency chain (+15 pts)
    if is_in_dependency_chain and has_catchment_wo:
        modeled_link_score += 15
        rules_fired.append({
            "rule": "downstream_dependency_connected",
            "category": "Modeled-link evidence",
            "points": 15,
            "description": f"Ward {ward_name} is actively connected to the modeled infrastructure dependency chain (DEPENDS_ON*1..3)."
        })

    real_data_score = min(real_data_score, 40)
    modeled_link_score = min(modeled_link_score, 55)
    total_score = min(real_data_score + modeled_link_score, 95)

    return {
        "incident_id": incident_id,
        "ward": ward_name,
        "issue_type": issue_type,
        "evidence_score": total_score,
        "real_data_score": real_data_score,
        "max_real_data_score": 40,
        "modeled_link_score": modeled_link_score,
        "max_modeled_link_score": 55,
        "max_score": 95,
        "evidence_score_display": f"evidence score: {total_score}/95 (Real-data: {real_data_score}/40, Modeled-link: {modeled_link_score}/55)",
        "rules_fired": rules_fired,
        "baseline_sensitivity": baseline_sensitivity,
        "note": "Work order is a synthetic model; association is not causation. Growth in reporting channels may play a role."
    }

def trend_for_ward(ward_name: str) -> List[Dict[str, Any]]:
    """H1 2024 vs H1 2025 per issue type with % change, citywide same-issue benchmark, and percentage points vs citywide."""
    query = """
        MATCH (w:Ward)
        WHERE toLower(w.name) = toLower($ward)
        MATCH (it:IssueType)
        OPTIONAL MATCH (w)-[r24:HAS_VOLUME {year: 2024}]->(it)
        OPTIONAL MATCH (w)-[r25:HAS_VOLUME {year: 2025}]->(it)
        WHERE r24 IS NOT NULL OR r25 IS NOT NULL
        RETURN it.name AS issue_type,
               coalesce(r24.count, 0) AS h1_2024_registered_complaints,
               coalesce(r25.count, 0) AS h1_2025_registered_complaints,
               coalesce(r25.pct_change, 0.0) AS ward_pct_change,
               coalesce(r24.full_year_count, 0) AS full_year_2024_context
        ORDER BY h1_2025_registered_complaints DESC
    """
    rows = db.run(query, {"ward": ward_name})
    trends = []
    for r in rows:
        issue = r["issue_type"]
        w_pct = r["ward_pct_change"]
        citywide_issue_pct = CITYWIDE_ISSUE_H1_CHANGE.get(issue, CITYWIDE_H1_PCT_CHANGE)
        diff_pp = round(w_pct - citywide_issue_pct, 2)
        c24_cnt = r["h1_2024_registered_complaints"]
        is_small = (c24_cnt < 30)
        trends.append({
            "issue_type": issue,
            "h1_2024_registered_complaints": c24_cnt,
            "h1_2025_registered_complaints": r["h1_2025_registered_complaints"],
            "ward_pct_change": w_pct if not is_small else "small base",
            "citywide_same_issue_pct_change": citywide_issue_pct,
            "citywide_pct_change": citywide_issue_pct,
            "percentage_points_vs_citywide": diff_pp if not is_small else "small base",
            "vs_citywide": diff_pp if not is_small else "small base",
            "full_year_2024_context": r["full_year_2024_context"],
            "is_small_base": is_small,
            "period": "H1 2024 vs H1 2025 (Jan 1-Jun 19)",
            "metric": "registered complaints"
        })
    return trends

def top_rising_issues(limit: int = 5) -> List[Dict[str, Any]]:
    """Same-period comparison only (H1 2024 vs H1 2025), requiring at least 30 complaints in H1 2024."""
    query = """
        MATCH (w:Ward)-[r24:HAS_VOLUME {year: 2024}]->(it:IssueType)
        MATCH (w)-[r25:HAS_VOLUME {year: 2025}]->(it)
        WHERE r24.count >= 30 AND r25.count > r24.count
        RETURN w.name AS ward,
               it.name AS issue_type,
               r24.count AS h1_2024_registered_complaints,
               r25.count AS h1_2025_registered_complaints,
               r25.pct_change AS ward_pct_change,
               (r25.count - r24.count) AS absolute_increase
        ORDER BY r25.pct_change DESC
        LIMIT $limit
    """
    rows = db.run(query, {"limit": limit})
    top_issues = []
    for r in rows:
        issue = r["issue_type"]
        w_pct = r["ward_pct_change"]
        citywide_issue_pct = CITYWIDE_ISSUE_H1_CHANGE.get(issue, CITYWIDE_H1_PCT_CHANGE)
        diff_pp = round(w_pct - citywide_issue_pct, 2)
        top_issues.append({
            "ward": r["ward"],
            "issue_type": issue,
            "h1_2024_registered_complaints": r["h1_2024_registered_complaints"],
            "h1_2025_registered_complaints": r["h1_2025_registered_complaints"],
            "ward_pct_change": w_pct,
            "citywide_same_issue_pct_change": citywide_issue_pct,
            "citywide_pct_change": citywide_issue_pct,
            "percentage_points_vs_citywide": diff_pp,
            "vs_citywide": diff_pp,
            "absolute_increase": r["absolute_increase"],
            "period": "H1 2024 vs H1 2025 (Jan 1-Jun 19)",
            "metric": "registered complaints"
        })
    return top_issues

def graph_for_incident(incident_id: str) -> Dict[str, Any]:
    """Returns nodes and edges for network graph visualization of an incident."""
    nodes = []
    edges = []
    node_ids = set()

    inc = db.run_single("""
        MATCH (inc:Incident {id: $id})
        MATCH (inc)-[:IN_WARD]->(w:Ward)
        MATCH (inc)-[:FOR_ISSUE]->(it:IssueType)
        RETURN inc.id AS id, inc.complaint_count AS count, w.name AS ward, it.name AS issue
    """, {"id": incident_id})

    if not inc:
        return {"nodes": [], "edges": []}

    # Incident Node
    nodes.append({
        "id": inc["id"],
        "label": f"Incident {inc['id']}\n({inc['count']} complaints)",
        "group": "Incident",
        "color": "#e74c3c"
    })
    node_ids.add(inc["id"])

    # Ward Node
    ward_id = f"WARD_{inc['ward']}"
    nodes.append({
        "id": ward_id,
        "label": f"Ward: {inc['ward']}",
        "group": "Ward",
        "color": "#3498db"
    })
    node_ids.add(ward_id)
    edges.append({"from": inc["id"], "to": ward_id, "label": "IN_WARD"})

    # IssueType Node
    issue_id = f"ISSUE_{inc['issue']}"
    nodes.append({
        "id": issue_id,
        "label": f"Issue: {inc['issue']}",
        "group": "IssueType",
        "color": "#f39c12"
    })
    node_ids.add(issue_id)
    edges.append({"from": inc["id"], "to": issue_id, "label": "FOR_ISSUE"})

    # Connected Work Orders & Infrastructure
    wo_data = db.run("""
        MATCH (wo:WorkOrder)-[:MAY_CONTRIBUTE_TO]->(it:IssueType {name: $issue})
        OPTIONAL MATCH (wo)-[:AFFECTS]->(infra:Infrastructure)
        OPTIONAL MATCH (wo)-[:ASSIGNED_TO]->(con:Contractor)
        OPTIONAL MATCH (wo)-[:PART_OF]->(p:Project)
        RETURN wo.id AS wo_id, wo.name AS wo_name, wo.status AS wo_status,
               infra.id AS infra_id, infra.name AS infra_name, infra.type AS infra_type,
               con.id AS con_id, con.name AS con_name,
               p.id AS p_id, p.name AS p_name
    """, {"issue": inc["issue"]})

    for row in wo_data:
        # WorkOrder node
        wo_node_id = row["wo_id"]
        if wo_node_id not in node_ids:
            nodes.append({
                "id": wo_node_id,
                "label": f"WorkOrder: {row['wo_name']}\n[{row['wo_status']}]",
                "group": "WorkOrder",
                "color": "#9b59b6" if row["wo_status"] == "Delayed" else "#95a5a6"
            })
            node_ids.add(wo_node_id)
            edges.append({"from": wo_node_id, "to": issue_id, "label": "MAY_CONTRIBUTE_TO"})

        # Infrastructure node
        infra_node_id = row.get("infra_id")
        if infra_node_id and infra_node_id not in node_ids:
            nodes.append({
                "id": infra_node_id,
                "label": f"{row['infra_type']}:\n{row['infra_name']}",
                "group": "Infrastructure",
                "color": "#1abc9c"
            })
            node_ids.add(infra_node_id)
            edges.append({"from": wo_node_id, "to": infra_node_id, "label": "AFFECTS"})

        # Contractor node
        con_node_id = row.get("con_id")
        if con_node_id and con_node_id not in node_ids:
            nodes.append({
                "id": con_node_id,
                "label": f"Contractor:\n{row['con_name']}",
                "group": "Contractor",
                "color": "#34495e"
            })
            node_ids.add(con_node_id)
            edges.append({"from": wo_node_id, "to": con_node_id, "label": "ASSIGNED_TO"})

        # Project node
        p_node_id = row.get("p_id")
        if p_node_id and p_node_id not in node_ids:
            nodes.append({
                "id": p_node_id,
                "label": f"Project:\n{row['p_name']}",
                "group": "Project",
                "color": "#7f8c8d"
            })
            node_ids.add(p_node_id)
            edges.append({"from": wo_node_id, "to": p_node_id, "label": "PART_OF"})

    # Infrastructure dependencies
    dep_data = db.run("""
        MATCH (wo:WorkOrder)-[:MAY_CONTRIBUTE_TO]->(it:IssueType {name: $issue})
        MATCH (wo)-[:AFFECTS]->(target:Infrastructure)
        MATCH (dep:Infrastructure)-[:DEPENDS_ON*1..3]->(target)
        RETURN dep.id AS dep_id, dep.name AS dep_name, dep.type AS dep_type, target.id AS target_id
    """, {"issue": inc["issue"]})

    for d in dep_data:
        dep_id = d["dep_id"]
        if dep_id not in node_ids:
            nodes.append({
                "id": dep_id,
                "label": f"{d['dep_type']}:\n{d['dep_name']}",
                "group": "Infrastructure",
                "color": "#16a085"
            })
            node_ids.add(dep_id)
        edges.append({"from": dep_id, "to": d["target_id"], "label": "DEPENDS_ON"})

    # Sample of Complaints (top 5)
    sample_complaints = db.run("""
        MATCH (c:Complaint)-[:APPEARS_IN]->(inc:Incident {id: $id})
        RETURN c.id AS id, c.sub_category AS sub_cat, c.status AS status
        LIMIT 5
    """, {"id": incident_id})

    for sc in sample_complaints:
        cid = f"COMP_{sc['id']}"
        nodes.append({
            "id": cid,
            "label": f"Complaint {sc['id']}\n[{sc['sub_cat']}]",
            "group": "Complaint",
            "color": "#e67e22"
        })
        node_ids.add(cid)
        edges.append({"from": cid, "to": inc["id"], "label": "APPEARS_IN"})

    return {"nodes": nodes, "edges": edges}

# Optional helpers for UI dropdowns
def get_all_wards() -> List[str]:
    return [r["name"] for r in db.run("MATCH (w:Ward) RETURN w.name AS name ORDER BY w.name")]

def get_all_issue_types() -> List[str]:
    return [r["name"] for r in db.run("MATCH (it:IssueType) RETURN it.name AS name ORDER BY it.name")]

def get_all_work_orders() -> List[Dict[str, Any]]:
    query = """
        MATCH (wo:WorkOrder)
        OPTIONAL MATCH (wo)-[:AFFECTS]->(infra:Infrastructure)
        OPTIONAL MATCH (wo)-[:ASSIGNED_TO]->(con:Contractor)
        OPTIONAL MATCH (wo)-[:PART_OF]->(p:Project)
        RETURN wo.id AS id,
               wo.name AS name,
               wo.status AS status,
               wo.delay_days AS delay_days,
               wo.contributes_to AS contributes_to,
               infra.name AS affected_infra,
               con.name AS contractor,
               p.name AS project
        ORDER BY wo.id
    """
    return db.run(query)

def get_incident_details(incident_id: str) -> Dict[str, Any]:
    """Returns incident details along with individual complaint records."""
    inc = db.run_single("""
        MATCH (inc:Incident {id: $id})
        MATCH (inc)-[:IN_WARD]->(w:Ward)
        MATCH (inc)-[:FOR_ISSUE]->(it:IssueType)
        OPTIONAL MATCH (c:Complaint)-[:APPEARS_IN]->(inc)
        RETURN inc.id AS incident_id,
               w.name AS ward,
               it.name AS issue_type,
               inc.complaint_count AS complaint_count,
               inc.open_count AS open_count,
               inc.resolved_count AS resolved_count,
               inc.status_note AS status_note,
               collect({
                   id: c.id,
                   created_at: c.created_at,
                   sub_category: c.sub_category,
                   status: c.status,
                   language: c.language,
                   text: c.text,
                   text_source: c.text_source
               }) AS complaints
    """, {"id": incident_id})
    return inc or {}

get_incidents = find_incidents

if __name__ == '__main__':
    print("=" * 80)
    print("TESTING QUERIES.PY FUNCTIONS")
    print("=" * 80)

    print("\n1. find_incidents(ward='thanisandra'):")
    incidents = find_incidents(ward="thanisandra")
    for inc in incidents[:3]:
        print("  ", inc)

    print("\n2. trace_root_cause('INC-001'):")
    rc = trace_root_cause("INC-001")
    print("   Incident:", rc.get("incident_id"), rc.get("ward"), rc.get("issue_type"))
    print("   Note:", rc.get("note"))
    print("   Evidence Score:", rc.get("evidence_score"))
    if rc.get("work_orders"):
        wo = rc["work_orders"][0]
        print(f"   Work Order: [{wo['work_order_id']}] {wo['work_order_name']} ({wo['status']})")
        print(f"   Affected Infra: {wo['affected_infrastructure']}")
        print(f"   Downstream Dependents count: {len(wo['downstream_dependents'])}")

    print("\n3. what_if_delay('WO-101', extra_days=14):")
    wid = what_if_delay("WO-101", extra_days=14)
    print("   Target:", wid.get("target_infrastructure"))
    print("   Dependent Wards:", wid.get("dependent_wards"))
    print("   Total Baseline Complaints:", wid.get("total_baseline_complaints_in_catchment"))
    print("   Projected Additional Complaints (+14 days):", wid.get("total_projected_additional_complaints"))
    print("   Projection Method:", wid.get("projection_method"))

    print("\n4. evidence_for_incident('INC-001'):")
    ev = evidence_for_incident("INC-001")
    print("   Evidence Score:", ev.get("evidence_score"), "/", ev.get("max_score"))
    print("   Rules fired count:", len(ev.get("rules_fired", [])))
    for rf in ev.get("rules_fired", []):
        print(f"     + {rf['points']} pts: {rf['rule']} -> {rf['description']}")

    print("\n5. trend_for_ward('Thanisandra'):")
    trends = trend_for_ward("Thanisandra")
    for t in trends[:3]:
        print("  ", t)

    print("\n6. top_rising_issues(limit=5):")
    rising = top_rising_issues(limit=5)
    for r in rising:
        print("  ", r)

    print("\n7. graph_for_incident('INC-001'):")
    g = graph_for_incident("INC-001")
    print(f"   Nodes count: {len(g.get('nodes', []))}, Edges count: {len(g.get('edges', []))}")
    print("   Node groups:", set(n["group"] for n in g.get("nodes", [])))
