import csv
import json
import random
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# Set random seed for reproducibility
random.seed(42)

DATA_DIR = Path(r"c:\Users\ANUSHREE R\civicgraph\data")
P_2025_FILE = DATA_DIR / "bbmp_grievances_2024.csv"  # File containing 2025 timestamps
P_2024_FILE = DATA_DIR / "bbmp_grievances_2025.csv"  # File containing 2024 timestamps

# Canonical 12 IssueTypes
CATEGORY_MAP = {
    'Electrical': 'Electrical',
    'Solid Waste (Garbage) Related': 'Solid Waste Management',
    'Plastic': 'Solid Waste Management',
    'Road Maintenance(Engg)': 'Road Maintenance',
    'Road Infrastructure': 'Road Maintenance',
    'Health Dept': 'Health',
    'CORONA COVID19': 'Health',
    'Forest': 'Forestry & Greenery',
    'Parks and Play grounds': 'Forestry & Greenery',
    'veterinary': 'Animal Husbandry',
    'Storm  Water Drain(SWD)': 'Storm Water Drain',
    'Water Crisis': 'Water Supply & Lakes',
    'Lakes': 'Water Supply & Lakes',
    'E khata / Khata services': 'Revenue & Khata',
    'Revenue Department': 'Revenue & Khata',
    'Property Tax services': 'Revenue & Khata',
    'Town Planning': 'Town Planning',
    'Estate': 'Town Planning',
    'Traffic Engineer Cell (TEC)': 'Traffic & Utilities',
    'Optical Fiber Cables (OFC)': 'Traffic & Utilities',
}

CANONICAL_ISSUE_TYPES = [
    'Electrical',
    'Solid Waste Management',
    'Road Maintenance',
    'Health',
    'Forestry & Greenery',
    'Animal Husbandry',
    'Storm Water Drain',
    'Water Supply & Lakes',
    'Revenue & Khata',
    'Town Planning',
    'Traffic & Utilities',
    'Other'
]

UNRESOLVED_STATUSES = {'Registered', 'ReOpen', 'In Progress'}

KANNADA_TEMPLATES = {
    'Solid Waste Management': [
        "ರಸ್ತೆ ಬದಿಯಲ್ಲಿ ಕಸದ ರಾಶಿ ಬಿದ್ದಿದ್ದು, ತೀವ್ರ ದುರ್ವಾಸನೆ ಬರುತ್ತಿದೆ ಮತ್ತು ನಾಯಿಗಳು ಹರಡುತ್ತಿವೆ.",
        "ಕಳೆದ ಮೂರು ದಿನಗಳಿಂದ ಕಸ ಸಂಗ್ರಹ ವಾಹನ ಬಂದಿಲ್ಲ, ದಯವಿಟ್ಟು ವಾಹನ ಕಳುಹಿಸಿ.",
        "ಖಾಲಿ ನಿವೇಶನದಲ್ಲಿ ಜನರು ನಿರಂತರವಾಗಿ ತ್ಯಾಜ್ಯ ಸುರಿಯುತ್ತಿದ್ದಾರೆ, ತಕ್ಷಣ ಸ್ವಚ್ಛಗೊಳಿಸಿ.",
        "ನಮ್ಮ ರಸ್ತೆಯಲ್ಲಿ ಪೌರಕಾರ್ಮಿಕರು ಕಸ ಗುಡಿಸುತ್ತಿಲ್ಲ, ರಸ್ತೆ ತುಂಬಾ ಕಸ ತುಂಬಿದೆ."
    ],
    'Electrical': [
        "ಬೀದಿ ದೀಪ ಕೆಟ್ಟುಹೋಗಿದ್ದು ರಾತ್ರಿ ವೇಳೆ ಕತ್ತಲೆಯಾಗಿದೆ, ಮಹಿಳೆಯರು ಮತ್ತು ಮಕ್ಕಳಿಗೆ ಸಂಚರಿಸಲು ಭಯವಾಗುತ್ತಿದೆ.",
        "ವಿದ್ಯುತ್ ಕಂಬದ ತಂತಿ ಸಡಿಲವಾಗಿದ್ದು ಅಪಾಯಕಾರಿಯಾಗಿದೆ, ತಕ್ಷಣ ದುರಸ್ತಿ ಮಾಡಿ.",
        "ಕಳೆದ ಒಂದು ವಾರದಿಂದ ಸತತವಾಗಿ ಬೀದಿ ದೀಪ ಬೆಳಗುತ್ತಿಲ್ಲ, ದಯವಿಟ್ಟು ಪರಿಶೀಲಿಸಿ."
    ],
    'Road Maintenance': [
        "ಮುಖ್ಯ ರಸ್ತೆಯಲ್ಲಿ ಆಳವಾದ ಗುಂಡಿಗಳು ಬಿದ್ದಿದ್ದು ದ್ವಿಚಕ್ರ ವಾಹನ ಸವಾರರು ಬಿದ್ದು ಗಾಯಗೊಳ್ಳುತ್ತಿದ್ದಾರೆ.",
        "ರಸ್ತೆ ಡಾಂಬರೀಕರಣ ಹಾಳಾಗಿದ್ದು ಮಳೆ ನೀರಿನಿಂದ ದೊಡ್ಡ ಕಂದಕಗಳು ಸೃಷ್ಟಿಯಾಗಿವೆ.",
        "ಪಾದಚಾರಿ ರಸ್ತೆ ಕಿತ್ತುಹೋಗಿದ್ದು ಸಾರ್ವಜನಿಕರ ಓಡಾಟಕ್ಕೆ ತೊಂದರೆಯಾಗಿದೆ."
    ],
    'Health': [
        "ಸೊಳ್ಳೆಗಳ ಹಾವಳಿ ಹೆಚ್ಚಾಗಿದ್ದು ಡೆಂಗ್ಯೂ ಭೀತಿ ಇದೆ, ದಯವಿಟ್ಟು ಫಾಗಿಂಗ್ ಮಾಡಿಸಿ.",
        "ಮುಚ್ಚದ ಚರಂಡಿ ನೀರಿನಿಂದ ಪ್ರದೇಶದಲ್ಲಿ ಅನಾರೋಗ್ಯ ಹರಡುವ ಸಾಧ್ಯತೆ ಇದೆ."
    ],
    'Forestry & Greenery': [
        "ಭಾರೀ ಮಳೆಗೆ ಮರದ ಕೊಂಬೆ ಮುರಿದು ರಸ್ತೆಗೆ ಬಿದ್ದಿದ್ದು ಸಂಚಾರ ಅಸ್ತವ್ಯಸ್ತವಾಗಿದೆ.",
        "ಒಣಗಿದ ಮರ ಯಾವುದೇ ಕ್ಷಣದಲ್ಲಿ ಬೀಳುವಂತಿದ್ದು ತಕ್ಷಣ ತೆರವುಗೊಳಿಸಿ."
    ],
    'Animal Husbandry': [
        "ಬೀದಿ ನಾಯಿಗಳ ಹಾವಳಿ ವಿಪರೀತವಾಗಿದ್ದು, ದಾರಿಹೋಕರ ಬೆನ್ನಟ್ಟಿ ಕಚ್ಚಲು ಬರುತ್ತಿವೆ.",
        "ರಸ್ತೆಯಲ್ಲಿ ಬೀಡಾಡಿ ದನಗಳು ಸಂಚಾರಕ್ಕೆ ಅಡ್ಡಿಯುಂಟುಮಾಡುತ್ತಿವೆ."
    ],
    'Storm Water Drain': [
        "ರಾಜಕಾಲುವೆ ಹೂಳು ತುಂಬಿ ಮಳೆ ನೀರು ರಸ್ತೆಗೆ ಹರಿಯುತ್ತಿದೆ, ತಕ್ಷಣ ಒಳಚರಂಡಿ ಸ್ವಚ್ಛಗೊಳಿಸಿ.",
        "ಮಳೆಗಾಲದ ಚರಂಡಿ ಮುಚ್ಚಿಹೋಗಿದ್ದು ತಗ್ಗು ಪ್ರದೇಶಗಳಿಗೆ ನೀರು ನುಗ್ಗುತ್ತಿದೆ."
    ],
    'Water Supply & Lakes': [
        "ಕೊಳವೆಬಾವಿ ದುರಸ್ತಿಯಲ್ಲಿದ್ದು ಕುಡಿಯುವ ನೀರಿನ ಸಮಸ್ಯೆ ತಲೆದೂರಿದೆ.",
        "ಕೆರೆಗೆ ಕೊಳಚೆ ನೀರು ಹರಿಯುತ್ತಿದ್ದು ನೀರು ಮಲಿನವಾಗಿದೆ."
    ],
    'Other': [
        "ಸಾರ್ವಜನಿಕ ಸಮಸ್ಯೆ ಬಗ್ಗೆ ದೂರು ನೀಡಿದರೂ ಯಾವುದೇ ಕ್ರಮ ಕೈಗೊಂಡಿಲ್ಲ, ಶೀಘ್ರ ಪರಿಹರಿಸಿ.",
        "ನಮ್ಮ ಬಡಾವಣೆಯಲ್ಲಿ ಸಾರ್ವಜನಿಕ ಸೌಲಭ್ಯಗಳ ಕೊರತೆ ಇದೆ, ಅಧಿಕಾರಿಗಳು ಭೇಟಿ ನೀಡಿ."
    ]
}

ENGLISH_TEMPLATES = {
    'Solid Waste Management': [
        "Garbage pile accumulating along the curb, emitting foul stench and attracting stray animals.",
        "Door-to-door garbage collection auto has not arrived for three consecutive days.",
        "Open vacant site being turned into an unauthorized black spot and garbage dump.",
        "Street sweeping not carried out by pourakarmikas, plastic debris scattered everywhere.",
        "Waste transfer vehicle spilling garbage during transport along the main road."
    ],
    'Electrical': [
        "Street light not functional for over 4 days, leaving entire stretch in complete darkness.",
        "Flickering sodium vapor bulb causing hazardous dark spots on the cross road.",
        "Exposed street light junction box at pedestrian level posing severe shock hazard."
    ],
    'Road Maintenance': [
        "Deep dangerous potholes after recent rains causing vehicle damage and water logging.",
        "Road surface peeled off exposing sharp gravel, dangerous for two-wheelers.",
        "Footpath pavers broken and missing, pedestrians forced to walk on busy carriageway."
    ],
    'Health': [
        "Severe mosquito menace and stagnation, high risk of dengue outbreak in the layout.",
        "Public health sanitation hazard due to open overflowing sewage drain."
    ],
    'Forestry & Greenery': [
        "Heavy fallen tree branch blocking vehicular passage after thunderstorm.",
        "Dead eucalyptus tree leaning dangerously toward overhead electric cables."
    ],
    'Animal Husbandry': [
        "Pack of aggressive stray dogs chasing two-wheelers and pedestrians at night.",
        "Dead stray animal carcass on the road margin requiring immediate clearance."
    ],
    'Storm Water Drain': [
        "Storm water drain choked with construction debris, storm water overflowing onto road.",
        "Damaged SWD retaining wall leading to bank erosion near residential compound."
    ],
    'Water Supply & Lakes': [
        "Severe drinking water scarcity in block, community borewell motor burnt out.",
        "Sewage inlet entering the local lake boundary, foul smell spreading."
    ],
    'Other': [
        "Public grievance pending without resolution for over two weeks, urgent intervention needed.",
        "Civic amenity maintenance request submitted by resident welfare association."
    ]
}

def map_issue(raw_cat):
    return CATEGORY_MAP.get(raw_cat.strip(), 'Other')

def generate_complaint_text(issue_type, sub_category, is_kannada):
    if is_kannada:
        templates = KANNADA_TEMPLATES.get(issue_type, KANNADA_TEMPLATES['Other'])
        return random.choice(templates)
    else:
        templates = ENGLISH_TEMPLATES.get(issue_type, ENGLISH_TEMPLATES['Other'])
        base = random.choice(templates)
        if sub_category and sub_category.lower() not in base.lower():
            return f"[{sub_category}] {base}"
        return base

def main():
    print("=" * 80)
    print("PREPARING CIVICGRAPH DATA PIPELINE (STAGE 2A & 2B)")
    print("=" * 80)

    # Cutoffs
    h1_end_2024 = "2024-06-19 23:59:59"
    h1_end_2025 = "2025-06-19 23:59:59"

    # Step 1: Collect all distinct canonical wards (from both files, excluding NON Ward)
    all_wards = set()
    
    # 2024 file counts
    h1_2024_counts = Counter()
    full_2024_counts = Counter()
    
    with open(P_2024_FILE, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for r in reader:
            w = r['Ward Name'].strip()
            if w == 'NON Ward' or not w:
                continue
            all_wards.add(w)
            d = r['Grievance Date'].strip()
            cat = r['Category'].strip()
            issue = map_issue(cat)
            full_2024_counts[(w, issue)] += 1
            if d <= h1_end_2024:
                h1_2024_counts[(w, issue)] += 1

    # 2025 file records and counts
    h1_2025_counts = Counter()
    ward_2025_totals = Counter()
    all_2025_records = []

    with open(P_2025_FILE, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for r in reader:
            w = r['Ward Name'].strip()
            if w == 'NON Ward' or not w:
                continue
            all_wards.add(w)
            d = r['Grievance Date'].strip()
            cat = r['Category'].strip()
            sub_cat = r['Sub Category'].strip()
            status = r['Grievance Status'].strip()
            if not status or status.lower() == 'null':
                status = 'Registered'
            issue = map_issue(cat)
            
            if d <= h1_end_2025:
                h1_2025_counts[(w, issue)] += 1
                ward_2025_totals[w] += 1
                all_2025_records.append({
                    'id': r['Complaint ID'].strip(),
                    'created_at': d,
                    'ward': w,
                    'category': cat,
                    'sub_category': sub_cat,
                    'status': status,
                    'issue_type': issue
                })

    sorted_wards = sorted(list(all_wards))
    print(f"Total Canonical Wards Identified: {len(sorted_wards)}")

    # 1. Write clean_wards.csv
    clean_wards_path = DATA_DIR / "clean_wards.csv"
    with open(clean_wards_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['ward_id', 'ward_name', 'source'])
        for idx, w in enumerate(sorted_wards, 1):
            writer.writerow([f"WARD_{idx:03d}", w, 'real'])
    print(f"Wrote {len(sorted_wards)} wards to {clean_wards_path.name}")

    # 2. Write clean_issue_types.csv
    clean_issues_path = DATA_DIR / "clean_issue_types.csv"
    with open(clean_issues_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['issue_id', 'issue_name', 'source'])
        for idx, issue in enumerate(CANONICAL_ISSUE_TYPES, 1):
            writer.writerow([f"ISSUE_{idx:02d}", issue, 'real'])
    print(f"Wrote {len(CANONICAL_ISSUE_TYPES)} issue types to {clean_issues_path.name}")

    # 3. Write clean_years.csv
    clean_years_path = DATA_DIR / "clean_years.csv"
    with open(clean_years_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['year', 'source'])
        writer.writerow(['2024', 'real'])
        writer.writerow(['2025', 'real'])
    print(f"Wrote 2 years to {clean_years_path.name}")

    # 4. Write clean_volumes.csv
    # Contains like-for-like H1 2024 vs H1 2025 per (ward, issue), % change, and full_year_2024_count as extra context
    clean_volumes_path = DATA_DIR / "clean_volumes.csv"
    volume_rows = []
    for w in sorted_wards:
        for issue in CANONICAL_ISSUE_TYPES:
            c24_h1 = h1_2024_counts.get((w, issue), 0)
            c25_h1 = h1_2025_counts.get((w, issue), 0)
            c24_full = full_2024_counts.get((w, issue), 0)
            pct = round(((c25_h1 - c24_h1) / c24_h1 * 100), 2) if c24_h1 > 0 else (100.0 if c25_h1 > 0 else 0.0)
            
            # Only save rows where there was at least 1 complaint across periods
            if c24_h1 > 0 or c25_h1 > 0 or c24_full > 0:
                volume_rows.append({
                    'ward_name': w,
                    'issue_type': issue,
                    'h1_2024_count': c24_h1,
                    'h1_2025_count': c25_h1,
                    'pct_change': pct,
                    'full_year_2024_count': c24_full,
                    'period': 'H1 2024 vs H1 2025 (Jan 1-Jun 19)',
                    'source': 'real'
                })

    with open(clean_volumes_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['ward_name', 'issue_type', 'h1_2024_count', 'h1_2025_count', 'pct_change', 'full_year_2024_count', 'period', 'source']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(volume_rows)
    print(f"Wrote {len(volume_rows)} HAS_VOLUME records to {clean_volumes_path.name}")

    # 5. Top 8 wards by 2025 volume
    top8_wards = [w for w, _ in ward_2025_totals.most_common(8)]
    print(f"Top 8 Wards by 2025 Volume: {top8_wards}")

    # 6. Sample real complaints for top 8 wards in the last 14 days (Jun 6 - Jun 19, 2025), cap at 2,000
    last_14d_start = "2025-06-06 00:00:00"
    last_14d_end = "2025-06-19 23:59:59"

    recent_complaints = [
        r for r in all_2025_records
        if r['ward'] in top8_wards and last_14d_start <= r['created_at'] <= last_14d_end
    ]
    # Load all complaints in the window without capping (2,487 records)
    recent_complaints.sort(key=lambda x: x['created_at'], reverse=True)
    clean_complaints = []
    for r in recent_complaints:
        is_kn = (random.random() < 0.20)
        lang = 'kn' if is_kn else 'en'
        text = generate_complaint_text(r['issue_type'], r['sub_category'], is_kn)
        clean_complaints.append({
            'complaint_id': r['id'],
            'created_at': r['created_at'],
            'ward': r['ward'],
            'category': r['category'],
            'sub_category': r['sub_category'],
            'status': r['status'],
            'issue_type': r['issue_type'],
            'text': text,
            'language': lang,
            'source': 'real',
            'text_source': 'synthetic'
        })

    clean_complaints_path = DATA_DIR / "clean_complaints.csv"
    with open(clean_complaints_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['complaint_id', 'created_at', 'ward', 'category', 'sub_category', 'status', 'issue_type', 'text', 'language', 'source', 'text_source']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(clean_complaints)
    print(f"Wrote {len(clean_complaints)} real complaints to {clean_complaints_path.name}")

    # 7. Form Incidents from loaded complaints (minimum 5 complaints per ward + issue)
    ISSUE_SLUG = {
        'Solid Waste Management': 'SolidWaste',
        'Electrical': 'Electrical',
        'Road Maintenance': 'RoadMaintenance',
        'Health': 'Health',
        'Forestry & Greenery': 'ForestryGreenery',
        'Animal Husbandry': 'AnimalHusbandry',
        'Storm Water Drain': 'StormWaterDrain',
        'Water Supply & Lakes': 'WaterSupplyLakes',
        'Revenue & Khata': 'RevenueKhata',
        'Town Planning': 'TownPlanning',
        'Traffic & Utilities': 'TrafficUtilities',
        'Other': 'Other'
    }

    incidents_grouped = defaultdict(list)
    for c in clean_complaints:
        incidents_grouped[(c['ward'], c['issue_type'])].append(c)

    # Precompute weekly baseline & spike per (ward, issue) across H1 2025
    ward_issue_weekly = defaultdict(lambda: Counter())
    for r in all_2025_records:
        dt = datetime.strptime(r['created_at'][:10], '%Y-%m-%d')
        wk = dt.isocalendar()[1]
        ward_issue_weekly[(r['ward'], r['issue_type'])][wk] += 1

    incidents_rows = []
    complaint_incident_map = {}

    # Ensure Thanisandra Solid Waste is primary
    primary_key = ('Thanisandra', 'Solid Waste Management')
    ordered_keys = [primary_key] + [k for k in sorted(incidents_grouped.keys()) if k != primary_key]

    for (w, issue) in ordered_keys:
        clist = incidents_grouped.get((w, issue), [])
        if len(clist) >= 5:
            ward_slug = w.replace(' ', '')
            issue_slug = ISSUE_SLUG.get(issue, 'Other')
            inc_id = f"INC-{ward_slug}-{issue_slug}"
            
            open_count = sum(1 for c in clist if c['status'] in UNRESOLVED_STATUSES)
            resolved_count = len(clist) - open_count

            # Calculate weekly baseline excluding spike week
            w_weeks = ward_issue_weekly.get((w, issue), Counter())
            if w_weeks:
                spk_wk, spk_cnt = w_weeks.most_common(1)[0]
                tot_c = sum(w_weeks.values())
                excl_c = tot_c - spk_cnt
                excl_w = max(len(w_weeks) - 1, 1)
                b_weekly = round(excl_c / excl_w, 1)
                spk_mult = round(spk_cnt / b_weekly, 2) if b_weekly > 0 else 1.0
            else:
                spk_wk, spk_cnt, b_weekly, spk_mult = 0, 0, 0.0, 1.0

            incidents_rows.append({
                'incident_id': inc_id,
                'ward': w,
                'issue_type': issue,
                'complaint_count': len(clist),
                'open_count': open_count,
                'resolved_count': resolved_count,
                'baseline_weekly': b_weekly,
                'spike_multiplier': spk_mult,
                'spike_week': spk_wk,
                'spike_complaints': spk_cnt,
                'status_note': "Status as of data export; recent complaints are more likely still open.",
                'source': 'real'
            })
            for c in clist:
                complaint_incident_map[c['complaint_id']] = inc_id

    clean_incidents_path = DATA_DIR / "clean_incidents.csv"
    with open(clean_incidents_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = [
            'incident_id', 'ward', 'issue_type', 'complaint_count', 'open_count',
            'resolved_count', 'baseline_weekly', 'spike_multiplier', 'spike_week',
            'spike_complaints', 'status_note', 'source'
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(incidents_rows)
    print(f"Wrote {len(incidents_rows)} incidents to {clean_incidents_path.name}")

    # Write complaint-to-incident link CSV
    clean_incident_links_path = DATA_DIR / "clean_complaint_incident_links.csv"
    with open(clean_incident_links_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['complaint_id', 'incident_id', 'source'])
        for cid, iid in complaint_incident_map.items():
            writer.writerow([cid, iid, 'real'])
    print(f"Wrote {len(complaint_incident_map)} APPEARS_IN links to {clean_incident_links_path.name}")

    # 8. Synthetic Dependency Layer (STAGE 2B)
    # 7 Infrastructure nodes:
    # - WasteProcessingPlant: "Central Processing Facility (modeled)"
    # - TransferStation: "Transfer Station TS-1 (modeled)" (in Thanisandra)
    # - CollectionRoutes:
    #   - "Thanisandra North Route (modeled)" in Thanisandra
    #   - "Thanisandra Commercial Corridor (modeled)" in Thanisandra
    #   - "Jakkur East Feeder Route (modeled)" in Jakkur
    #   - "Horamavu Link Route (modeled)" in Horamavu
    #   - "Bellandur Outer Feeder (modeled)" in Bellandur
    #
    # All CollectionRoutes DEPENDS_ON TS-1; TS-1 DEPENDS_ON Central Processing Facility
    #
    # 3 Contractors: Contractor A (modeled), Contractor B (modeled), Contractor C (modeled)
    # 2 Projects: "Solid Waste Segregation & Route Upgrade (modeled)", "Facility Modernization Phase 1 (modeled)"
    # 5 Work Orders:
    #   - WO-101: "Transfer Station TS-1 Compactor & Conveyor Overhaul (modeled)", status: "Delayed", affects: "Transfer Station TS-1 (modeled)", contributes_to: "Solid Waste Management"
    #   - WO-102: "Primary Fleet Route Re-Alignment (modeled)", status: "Delayed", affects: "Thanisandra North Route (modeled)", contributes_to: "Solid Waste Management"
    #   - WO-103: "Processing Facility Bio-Methanization Expansion (modeled)", status: "In Progress", affects: "Central Processing Facility (modeled)", contributes_to: "Solid Waste Management"
    #   - WO-104: "Secondary Segregation Hopper Maintenance (modeled)", status: "Completed", affects: "Transfer Station TS-1 (modeled)", contributes_to: "Solid Waste Management"
    #   - WO-105: "Jakkur Feeder Route Drainage Clearance (modeled)", status: "Completed", affects: "Jakkur East Feeder Route (modeled)", contributes_to: "Solid Waste Management"

    synthetic_data = {
        'infrastructure': [
            {'id': 'INFRA-WPP', 'name': 'Central Processing Facility (modeled)', 'type': 'WasteProcessingPlant', 'ward': 'Thanisandra', 'source': 'synthetic'},
            {'id': 'INFRA-TS1', 'name': 'Transfer Station TS-1 (modeled)', 'type': 'TransferStation', 'ward': 'Thanisandra', 'source': 'synthetic'},
            {'id': 'INFRA-CR-TH1', 'name': 'Thanisandra North Route (modeled)', 'type': 'CollectionRoute', 'ward': 'Thanisandra', 'source': 'synthetic'},
            {'id': 'INFRA-CR-TH2', 'name': 'Thanisandra Commercial Corridor (modeled)', 'type': 'CollectionRoute', 'ward': 'Thanisandra', 'source': 'synthetic'},
            {'id': 'INFRA-CR-JK', 'name': 'Jakkur East Feeder Route (modeled)', 'type': 'CollectionRoute', 'ward': 'Jakkur', 'source': 'synthetic'},
            {'id': 'INFRA-CR-HM', 'name': 'Horamavu Link Route (modeled)', 'type': 'CollectionRoute', 'ward': 'Horamavu', 'source': 'synthetic'},
            {'id': 'INFRA-CR-BL', 'name': 'Bellandur Outer Feeder (modeled)', 'type': 'CollectionRoute', 'ward': 'Bellandur', 'source': 'synthetic'},
        ],
        'infra_dependencies': [
            {'from': 'INFRA-CR-TH1', 'to': 'INFRA-TS1', 'type': 'DEPENDS_ON', 'source': 'synthetic'},
            {'from': 'INFRA-CR-TH2', 'to': 'INFRA-TS1', 'type': 'DEPENDS_ON', 'source': 'synthetic'},
            {'from': 'INFRA-CR-JK', 'to': 'INFRA-TS1', 'type': 'DEPENDS_ON', 'source': 'synthetic'},
            {'from': 'INFRA-CR-HM', 'to': 'INFRA-TS1', 'type': 'DEPENDS_ON', 'source': 'synthetic'},
            {'from': 'INFRA-CR-BL', 'to': 'INFRA-TS1', 'type': 'DEPENDS_ON', 'source': 'synthetic'},
            {'from': 'INFRA-TS1', 'to': 'INFRA-WPP', 'type': 'DEPENDS_ON', 'source': 'synthetic'},
        ],
        'contractors': [
            {'id': 'CONT-01', 'name': 'Contractor A (modeled)', 'source': 'synthetic'},
            {'id': 'CONT-02', 'name': 'Contractor B (modeled)', 'source': 'synthetic'},
            {'id': 'CONT-03', 'name': 'Contractor C (modeled)', 'source': 'synthetic'},
        ],
        'projects': [
            {'id': 'PROJ-01', 'name': 'Solid Waste Segregation & Route Upgrade (modeled)', 'source': 'synthetic'},
            {'id': 'PROJ-02', 'name': 'Facility Modernization Phase 1 (modeled)', 'source': 'synthetic'},
        ],
        'work_orders': [
            {
                'id': 'WO-101',
                'name': 'Transfer Station TS-1 Compactor & Conveyor Overhaul (modeled)',
                'status': 'Delayed',
                'delay_days': 45,
                'target_infra': 'INFRA-TS1',
                'contractor': 'CONT-01',
                'project': 'PROJ-01',
                'contributes_to': 'Solid Waste Management',
                'source': 'synthetic'
            },
            {
                'id': 'WO-102',
                'name': 'Primary Fleet Route Re-Alignment (modeled)',
                'status': 'Delayed',
                'delay_days': 20,
                'target_infra': 'INFRA-CR-TH1',
                'contractor': 'CONT-02',
                'project': 'PROJ-01',
                'contributes_to': 'Solid Waste Management',
                'source': 'synthetic'
            },
            {
                'id': 'WO-103',
                'name': 'Processing Facility Bio-Methanization Expansion (modeled)',
                'status': 'In Progress',
                'delay_days': 0,
                'target_infra': 'INFRA-WPP',
                'contractor': 'CONT-03',
                'project': 'PROJ-02',
                'contributes_to': 'Solid Waste Management',
                'source': 'synthetic'
            },
            {
                'id': 'WO-104',
                'name': 'Secondary Segregation Hopper Maintenance (modeled)',
                'status': 'Completed',
                'delay_days': 0,
                'target_infra': 'INFRA-TS1',
                'contractor': 'CONT-01',
                'project': 'PROJ-01',
                'contributes_to': 'Solid Waste Management',
                'source': 'synthetic'
            },
            {
                'id': 'WO-105',
                'name': 'Jakkur Feeder Route Drainage Clearance (modeled)',
                'status': 'Completed',
                'delay_days': 0,
                'target_infra': 'INFRA-CR-JK',
                'contractor': 'CONT-02',
                'project': 'PROJ-02',
                'contributes_to': 'Solid Waste Management',
                'source': 'synthetic'
            }
        ]
    }

    synthetic_file_path = DATA_DIR / "clean_synthetic_layer.json"
    with open(synthetic_file_path, 'w', encoding='utf-8') as f:
        json.dump(synthetic_data, f, indent=2)
    print(f"Wrote synthetic dependency layer to {synthetic_file_path.name}")

    print("\nData preparation complete!")

if __name__ == '__main__':
    main()

