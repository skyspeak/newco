#!/usr/bin/env python3
"""Coarse sector bucketing, used ONLY to TEST the map -- never to build it.

Why this module exists: the naive twin test compared index-label word tokens, so
"Healthcare" vs "Hospitals & Health Care" looked like zero overlap and two hospital
systems were reported as a cross-industry twin. That is a wording artifact.

Two independent readings are produced, and their disagreement is a finding:
  sector_from_labels -- what the "best places to work" index says the firm is
  sector_from_tags   -- what the firm's own extracted capabilities say it is

sector_from_tags SCORES every rule against every tag and takes the argmax. An earlier
first-match version was fragile in exactly the ways you would predict: "hospitality"
matched a `hospital` pattern and put Hilton in healthcare, and a single `software-...`
tag put General Motors in technology. Voting fixes both.
"""
import re, collections

# ---- from the index's industry label (ordered, first match wins: labels are short)
RULES = [
    ("hospitality-travel",  r"hospitality|hotel|lodging|travel|resort|casino|cruise|leisure|restaurant|food (and )?beverage|coffee|dining"),
    ("healthcare-provider", r"hospital(s|ity)?\b(?! ?ity)|health care|healthcare|health system|clinic|medical center|nursing|patient care|veterinar"),
    ("pharma-biotech",      r"pharmaceutic|biotech|drug|life science|medical (device|equipment)|diagnostic"),
    ("financial-services",  r"financ|bank|insur|invest|capital market|credit|wealth|asset manage|payment|fintech|accounting|audit"),
    ("technology",          r"software|internet|information technology|it services|computer|semiconduct|electronics manufactur|technology|saas|cloud|telecommunicat|\bdata\b"),
    ("retail-consumer",     r"retail|grocer|supermarket|apparel|fashion|footwear|furniture|consumer (goods|products)|merchandis|e-?commerce|department store|wholesale"),
    ("aerospace-defense",   r"aerospace|defen[cs]e|space|munition|military"),
    ("transport-logistics", r"logistic|freight|parcel|courier|airline|air transport|rail|trucking|shipping|supply chain|transportation|delivery|distribut"),
    ("industrial-manufacturing", r"manufactur|machinery|industrial|chemical|steel|mining|metal|appliance|automotive|motor vehicle|equipment|production"),
    ("energy-utilities",    r"energy|utilit|\boil\b|\bgas\b|petroleum|electric power|renewable|solar|nuclear"),
    ("media-entertainment", r"entertainment|media|broadcast|publish|film|music|gaming|computer games|sports|advertis"),
    ("professional-services", r"consult|professional services|staffing|recruit|legal|law firm|engineering services|architect|real estate|construction"),
    ("education-government-nonprofit", r"education|university|school|government|public administration|nonprofit|non-profit|administration programs"),
]

# ---- from the firm's own capability tags (SCORED: every pattern votes)
# weights let a decisive capability outvote an incidental one -- almost every large
# firm has some software tag, so software must not be allowed to win on its own.
TAG_RULES = {
    "healthcare-provider": [
        (r"clinical-care|patient-care|physician|primary-care|value-based-care|hospital-operations|nurs|acute-care|behavioral-health|urgent-care|telehealth", 3),
        (r"pharmacy-benefit|claims-adjudication|population-health|medical-record", 1),
    ],
    "pharma-biotech": [
        (r"drug-development|clinical-trial|pharmaceutic|biolog|therap|vaccine|molecul|regulatory-submission|gene|oncology|immunolog", 3),
        (r"medical-device|diagnostic|lab-instrument", 2),
    ],
    "financial-services": [
        (r"lending|banking|underwrit|capital-market|payment-(processing|network)|wealth|asset-custody|actuarial|investment-banking|brokerage|deposit|mortgage|credit-card|insurance", 3),
        (r"fraud-detection|claims-adjudication|core-transaction-processing|treasury", 2),
    ],
    "technology": [
        (r"cloud-infrastructure|saas|developer-(platform|ecosystem)|semiconductor-(design|fabrication)|operating-system|mobile-os|data-cent(er|re)|search-engine|app-marketplace|ai-and-machine-learning|cybersecurity", 3),
        (r"software-engineering|software-defined|api-|devops", 1),
    ],
    "transport-logistics": [
        (r"last-mile|air-express|package-sortation|freight|line-haul|parcel|fulfillment-network|logistics-network|cold-chain|fleet-(operations|services)|warehouse-operations", 3),
        (r"supply-chain-management|customs|distribution", 1),
    ],
    "retail-consumer": [
        (r"retail-store-operations|store-network|merchandis|grocery-retail|private-label|omnichannel-retail|e-commerce-operations|inventory-management|point-of-sale", 3),
        (r"loyalty-programs|consumer-brand|category-management", 1),
    ],
    "food-restaurant": [
        (r"restaurant-operations|quick-service|menu|food-preparation|kitchen|beverage-production|coffee-roast|franchise-licensing|food-safety", 3),
        (r"cold-chain-logistics", 1),
    ],
    "industrial-manufacturing": [
        (r"vehicle-manufacturing|discrete-manufacturing|semiconductor-fabrication|assembly-plant|machining|industrial-automation|dealer-network|electric-vehicle|chemical-production|steel|heavy-equipment|process-plant", 3),
        (r"supply-chain-management|quality-assurance|field-service-technicians", 1),
    ],
    "aerospace-defense": [
        (r"defense|missile|radar|electronic-warfare|satellite|airframe|classified|weapon|space-(system|launch)|govcon|federal-contract", 3),
        (r"program-management|systems-engineering", 1),
    ],
    "energy-utilities": [
        (r"upstream-oil|downstream-refin|drilling|refin|grid|power-generation|utility|pipeline|fuel-retail|renewable", 3),
    ],
    "hospitality-travel": [
        (r"hotel|lodging|guest|resort|theme-park|scheduled-passenger-air|cabin|in-flight|reservation|room-night|select-service", 3),
        (r"revenue-management-and-pricing|loyalty-programs", 1),
    ],
    "media-entertainment": [
        (r"ad-inventory|content-(production|licensing)|streaming|studio|broadcast|box-office|theatrical|music|sports-league|game-development", 3),
    ],
    "professional-services": [
        (r"management-consulting|audit-and-assurance|tax-advisory|staffing|construction-management|infrastructure-engineering|urban-planning|architecture|legal|transaction-advisory|systems-integration", 3),
        (r"program-management|change-management", 1),
    ],
    "education-government-nonprofit": [
        (r"public-program-administration|benefits-eligibility|student|curriculum|academic|government-services|medicaid", 3),
    ],
}
_COMPILED = {s: [(re.compile(p), w) for p, w in pats] for s, pats in TAG_RULES.items()}

def sector_from_labels(labels):
    blob = " ; ".join(labels or []).lower()
    if not blob.strip():
        return None
    for name, rx in RULES:
        if re.search(rx, blob):
            return name
    return None

def sector_from_tags(tags):
    """Score every sector against every tag; argmax wins. Ties -> 'unclassified'."""
    blob = " ".join(tags or []).lower()
    if not blob.strip():
        return "unclassified"
    score = collections.Counter()
    for sec, pats in _COMPILED.items():
        for rx, w in pats:
            hits = len(rx.findall(blob))
            if hits:
                score[sec] += w * min(hits, 4)
    if not score:
        return "unclassified"
    top = score.most_common(2)
    if len(top) > 1 and top[0][1] == top[1][1]:
        return "unclassified"
    return top[0][0]

def sector(labels, tags):
    return sector_from_labels(labels) or sector_from_tags(tags)
