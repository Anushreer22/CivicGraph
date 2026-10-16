import db, json

q = '''
MATCH (inc:Incident)-[:IN_WARD]->(w:Ward)
MATCH (inc)-[:FOR_ISSUE]->(it:IssueType)
RETURN inc.id AS id, w.name AS ward, it.name AS issue,
       inc.complaint_count AS count,
       coalesce(inc.baseline_weekly, 0.0) AS baseline_weekly,
       coalesce(inc.spike_multiplier, 1.0) AS spike_multiplier,
       coalesce(inc.spike_week, 0) AS spike_week,
       coalesce(inc.spike_complaints, 0) AS spike_complaints
'''
incs = db.run(q)

CITYWIDE_ISSUE_H1_CHANGE = {
    'Animal Husbandry': 322.51, 'Electrical': 45.43, 'Forestry & Greenery': 16.60,
    'Health': 73.71, 'Other': 177.42, 'Revenue & Khata': 1843.06,
    'Road Maintenance': 48.42, 'Solid Waste Management': 64.38,
    'Storm Water Drain': 27.35, 'Town Planning': -30.70,
    'Traffic & Utilities': 144.30, 'Water Supply & Lakes': -12.27
}

CITYWIDE_ISSUE_WEEK_RATIOS = {
    'Solid Waste Management': {20: 0.86, 21: 1.39, 22: 1.14, 23: 1.32, 24: 2.58, 25: 1.32},
    'Electrical': {20: 0.99, 21: 1.35, 22: 1.44, 23: 1.25, 24: 1.28, 25: 0.82},
    'Road Maintenance': {20: 1.50, 21: 2.54, 22: 1.11, 23: 1.03, 24: 1.68, 25: 0.71},
    'Animal Husbandry': {20: 1.35, 21: 1.49, 22: 1.34, 23: 1.23, 24: 1.59, 25: 1.05},
    'Forestry & Greenery': {20: 2.11, 21: 2.89, 22: 1.73, 23: 1.22, 24: 1.91, 25: 1.22},
    'Health': {20: 1.25, 21: 0.96, 22: 1.74, 23: 2.07, 24: 1.59, 25: 1.19},
    'Other': {20: 1.06, 21: 1.29, 22: 0.81, 23: 0.81, 24: 0.90, 25: 0.59},
    'Storm Water Drain': {20: 1.44, 21: 3.13, 22: 1.23, 23: 1.42, 24: 2.44, 25: 1.23},
    'Revenue & Khata': {20: 1.29, 21: 0.90, 22: 0.90, 23: 0.80, 24: 1.02, 25: 0.89},
    'Town Planning': {20: 0.95, 21: 0.70, 22: 0.70, 23: 1.11, 24: 1.15, 25: 0.82},
    'Traffic & Utilities': {20: 1.45, 21: 1.88, 22: 0.64, 23: 0.51, 24: 0.77, 25: 1.31},
    'Water Supply & Lakes': {20: 1.64, 21: 1.36, 22: 0.73, 23: 0.64, 24: 0.59, 25: 0.17}
}

results = []
for inc in incs:
    w = inc['ward']
    issue = inc['issue']
    count = inc['count']
    spk_cnt = inc['spike_complaints']
    spk_mult = inc['spike_multiplier']
    spk_wk = inc['spike_week']
    b_weekly = inc['baseline_weekly']

    # YoY trend
    trend = db.run_single('''
        MATCH (w:Ward {name: $ward})
        OPTIONAL MATCH (w)-[r24:HAS_VOLUME {year: 2024}]->(it:IssueType {name: $issue})
        OPTIONAL MATCH (w)-[r25:HAS_VOLUME {year: 2025}]->(it)
        RETURN coalesce(r25.pct_change, 0.0) AS pct
    ''', {'ward': w, 'issue': issue})
    pct = trend['pct'] if trend else 0.0
    city_pct = CITYWIDE_ISSUE_H1_CHANGE.get(issue, 64.38)
    diff_pp = round(pct - city_pct, 2)

    # Citywide week ratio
    c_ratio = CITYWIDE_ISSUE_WEEK_RATIOS.get(issue, {}).get(spk_wk, 1.0)
    unrounded_ror = spk_mult / c_ratio if c_ratio > 0 else 1.0

    # Work orders & infra
    wo_cnt = db.run_single('''
        MATCH (wo:WorkOrder)-[:MAY_CONTRIBUTE_TO]->(it:IssueType {name: $issue})
        MATCH (wo)-[:AFFECTS]->(target:Infrastructure)
        WHERE (target)-[:LOCATED_IN]->(:Ward {name: $ward})
           OR (target)<-[:DEPENDS_ON*1..3]-(:Infrastructure)-[:LOCATED_IN]->(:Ward {name: $ward})
        RETURN count(wo) AS cnt
    ''', {'ward': w, 'issue': issue})
    has_catchment = bool(wo_cnt and wo_cnt['cnt'] > 0)

    has_delayed = db.run_single('''
        MATCH (wo:WorkOrder {status: 'Delayed'})-[:MAY_CONTRIBUTE_TO]->(it:IssueType {name: $issue})
        MATCH (wo)-[:AFFECTS]->(target:Infrastructure)-[:LOCATED_IN]->(:Ward {name: $ward})
        RETURN count(wo) AS cnt
    ''', {'ward': w, 'issue': issue})
    delayed_in_ward = bool(has_delayed and has_delayed['cnt'] > 0)

    rules = []
    rd_score = 0
    md_score = 0

    if count >= 10:
        rd_score += 15
        rules.append('count_gte_10 (+15)')

    # SPIKE RULE: unrounded ratio-of-ratios to 1.5 (no rounding up), and peak week >= 30 complaints
    if spk_cnt >= 30 and unrounded_ror >= 1.5:
        if spk_mult >= 3.0:
            rd_score += 15
            rules.append(f'spike_vs_baseline (+15, ror={unrounded_ror:.3f}, cnt={spk_cnt})')
        elif spk_mult >= 2.0:
            rd_score += 10
            rules.append(f'spike_vs_baseline (+10, ror={unrounded_ror:.3f}, cnt={spk_cnt})')
        elif spk_mult >= 1.5:
            rd_score += 5
            rules.append(f'spike_vs_baseline (+5, ror={unrounded_ror:.3f}, cnt={spk_cnt})')

    if diff_pp >= 10.0:
        rd_score += 10
        rules.append(f'volume_up_vs_citywide (+10, diff={diff_pp:+.2f}pp)')

    if delayed_in_ward:
        md_score += 25
        rules.append('delayed_work_order_in_ward (+25)')

    if has_catchment:
        md_score += 15
        rules.append('may_contribute_to_matches_issue (+15)')
        md_score += 15
        rules.append('downstream_dependency_connected (+15)')

    tot = rd_score + md_score
    results.append({
        'id': inc['id'],
        'ward': w,
        'issue': issue,
        'total': tot,
        'real_data': rd_score,
        'modeled': md_score,
        'unrounded_ror': round(unrounded_ror, 3),
        'spk_cnt': spk_cnt,
        'rules': rules
    })

results.sort(key=lambda x: (x['total'], x['real_data']), reverse=True)
for r in results[:10]:
    rule_str = ', '.join(r['rules'])
    print(f"{r['id']}: total={r['total']} (real={r['real_data']}/40, mod={r['modeled']}/55)")
    print(f"   rules: {rule_str}")
    print(f"   unrounded_ror={r['unrounded_ror']:.3f}, spk_cnt={r['spk_cnt']}")
