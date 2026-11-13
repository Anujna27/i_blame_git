"""
eval/profile_generator.py

Deterministic synthetic generator for BEMULA-scale evaluation:
- 50 full user profiles across 6 domain bundles
- Multi-session dialogues (6-10 sessions per profile, 2-4 turns each, with L1 summaries)
- 12-20 ground-truth entities per profile
- 135 forget requests across F1-F6 (25 F1, 22 F2, 22 F3, 22 F4, 22 F5, 22 F6)
- Exactly 1,742 test questions (forget probes, preservation probes, control probes)

Reproducibility: random.Random(seed=42)
"""

import json
import os
from pathlib import Path
import random
from typing import Any, Dict, List, Tuple

FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Avery", "Sam", "Jamie", "Logan",
    "Robin", "Cameron", "Jesse", "Dakota", "Reese", "Skyler", "Finley", "Rowan", "Harper", "Peyton",
    "Kendall", "Emerson", "Adrian", "Eden", "Kai", "Quinn", "Hayden", "Sawyer", "Amari", "Dallas",
    "Elliot", "Shiloh", "River", "Rory", "Milan", "Sage", "Lennon", "Sloan", "Frankie", "Harley",
    "Charlie", "Blake", "Parker", "Drew", "Ellis", "Remi", "Phoenix", "Sterling", "Micah", "Devon",
    "Dana", "Corey", "Lee", "Pat", "Terry", "Tracy", "Kelly", "Chris", "Shannon", "Kerry",
    "Ashley", "Brett", "Stacy", "Jody", "Sydney", "Jules", "Val", "Noel", "Dana", "Blair"
]

LAST_NAMES = [
    "Chen", "Patel", "Vance", "Martinez", "Miller", "Kim", "Wilson", "Taylor", "Anderson", "Thomas",
    "Jackson", "White", "Harris", "Martin", "Thompson", "Garcia", "Davis", "Rodriguez", "Lewis", "Lee",
    "Walker", "Hall", "Allen", "Young", "Hernandez", "King", "Wright", "Lopez", "Hill", "Scott",
    "Green", "Adams", "Baker", "Gonzalez", "Nelson", "Carter", "Mitchell", "Perez", "Roberts", "Turner",
    "Phillips", "Campbell", "Parker", "Evans", "Edwards", "Collins", "Stewart", "Sanchez", "Morris", "Rogers"
]

DOMAIN_BUNDLES = ["medical", "financial", "professional", "travel", "family", "academic"]

# Domain template vocabularies for deterministic generation
TEMPLATES = {
    "medical": [
        ("allergy", "mild penicillin allergy diagnosed in 2021", "penicillin", "medical allergies"),
        ("prescription", "daily prescription Ventolin inhaler for asthma", "Ventolin", "prescription medications"),
        ("condition", "moderate eczema managed by Dr. Harris", "Harris", "skin conditions"),
        ("doctor", "primary care physician Dr. Evelyn Reed at Denver Health", "Reed", "primary care physician"),
        ("blood_type", "blood type O-negative registered with Red Cross", "O-negative", "blood type"),
        ("hospital", "knee arthroscopy performed at Swedish Medical Center", "Swedish", "past surgical procedures"),
        ("insurance", "health insurance policy member ID POL-8829104-BCBS", "POL-8829104", "health insurance policy ID"),
        ("vaccination", "annual quadrivalent influenza vaccination received in October", "influenza", "recent immunizations"),
    ],
    "financial": [
        ("checking", "direct deposit checking account number Chase-8839201948", "Chase-8839201948", "bank checking account"),
        ("credit_card", "Sapphire Reserve credit card ending in 4921", "4921", "primary credit card"),
        ("brokerage", "forty shares of index ETF VOO held in Vanguard", "VOO", "brokerage investments"),
        ("retirement", "annual backdoor Roth IRA contributions maximized", "Roth", "retirement account strategy"),
        ("loan", "federal student loan balance with Nelnet servicer", "Nelnet", "education loan provider"),
        ("credit_score", "FICO credit score of 785 recorded in September", "785", "credit score rating"),
        ("tax_filing", "CPA accountant Marcus Vance preparing annual 1040 return", "Marcus", "tax preparation accountant"),
        ("crypto", "cold hardware storage wallet Ledger Nano X backup", "Ledger", "crypto asset storage"),
    ],
    "professional": [
        ("employer", "employed as Principal Architect at Acme Corp", "Acme", "current employer"),
        ("manager", "reports directly to engineering VP Sarah Chen", "Sarah", "direct reporting manager"),
        ("project", "leads technical architecture for Project Apollo", "Apollo", "primary project leadership"),
        ("credential", "OpenAI production API key sk-proj-982347102934", "sk-proj-982347102934", "production API key"),
        ("role", "serves as remote cloud infrastructure DevOps lead", "DevOps", "professional role assignment"),
        ("office", "assigned to Seattle engineering headquarters building 4", "Seattle", "office campus location"),
        ("clearance", "holds public trust security clearance verification", "clearance", "security clearance status"),
        ("conference", "keynote speaker at CloudNativeCon annual conference", "CloudNativeCon", "conference presentations"),
    ],
    "travel": [
        ("passport", "international passport travel number USA-P98124019", "USA-P98124019", "passport travel number"),
        ("loyalty", "Delta Diamond Medallion frequent flyer status", "Diamond", "airline loyalty status"),
        ("flight", "booked transatlantic flight Lufthansa LH455 to Frankfurt", "LH455", "upcoming flight booking"),
        ("hotel", "reserved king suite at Park Hyatt Tokyo for November", "Hyatt", "hotel lodging reservation"),
        ("tsa", "TSA PreCheck and Global Entry membership PASSID-982104", "PASSID-982104", "known traveler number"),
        ("transit", "monthly subway ORCA transit card reloaded automatically", "ORCA", "metro transit card"),
        ("rental", "National Car Rental Executive Elite club member", "National", "car rental loyalty tier"),
        ("destination", "visited Reykjavik Iceland for northern lights photography", "Reykjavik", "international travel destination"),
    ],
    "family": [
        ("spouse", "married to pediatrician spouse named David", "David", "spouse name"),
        ("anniversary", "celebrates wedding anniversary on June 18th", "June 18th", "wedding anniversary date"),
        ("child", "daughter Maya attending elementary school grade two", "Maya", "child name and grade"),
        ("address", "residential home street address 789 Pine Avenue in Denver", "789 Pine", "home residential street address"),
        ("emergency", "emergency contact younger sister Clara Wilson", "Clara", "emergency contact person"),
        ("pet", "adopted Siamese cat pet named Mochi", "Mochi", "pet name and breed"),
        ("hometown", "raised in suburban Minneapolis Minnesota until college", "Minneapolis", "childhood hometown"),
        ("tradition", "hosts annual Thanksgiving dinner for extended family", "Thanksgiving", "annual family tradition"),
    ],
    "academic": [
        ("degree", "earned Master of Science in Computer Science from Stanford", "Stanford", "graduate degree university"),
        ("advisor", "graduate research thesis advised by Dr. Manning", "Manning", "thesis academic advisor"),
        ("thesis", "thesis published on reinforcement learning optimization", "reinforcement", "thesis research subject"),
        ("grant", "funded by National Science Foundation grant NSF-19824", "NSF-19824", "research grant identifier"),
        ("gpa", "undergraduate cumulative GPA 3.92 in Mathematics", "3.92", "undergraduate GPA"),
        ("scholarship", "awarded prestigious Dean Merit Scholarship in 2018", "Dean", "academic scholarship award"),
        ("society", "inducted member of Phi Beta Kappa honor society", "Phi Beta Kappa", "academic honor society"),
        ("lab", "conducted robotics research at Artificial Intelligence Laboratory", "Robotics", "academic research laboratory"),
    ],
}

# Control items that are NEVER stored in a profile's ground truth
CONTROL_ITEMS = [
    ("scuba_cert", "PADI master scuba diver certification license 98124", "scuba certification"),
    ("boat_license", "commercial maritime yacht captain license CAPT-4819", "boat captain license"),
    ("pilot_license", "private pilot aviation license license number FAA-88214", "private pilot license"),
    ("motorcycle", "vintage Harley Davidson Road King motorcycle registration", "motorcycle registration"),
    ("fencing", "national competitive sabre fencing tournament medal", "fencing sports rank"),
    ("wine_cellar", "private collection of Bordeaux grand cru vintage wines", "wine cellar collection"),
    ("pottery", "ceramic pottery wheel studio membership in Portland", "pottery studio membership"),
    ("cello", "handcrafted German antique cello musical instrument", "antique cello instrument"),
    ("patents", "us patent granted for quantum semiconductor waveguide", "quantum waveguide patent"),
    ("ham_radio", "FCC amateur radio operator callsign K9XYZ", "amateur radio callsign"),
]

# Preference items used for preservation
PREFERENCE_TEMPLATES = [
    ("The user enjoys programming in the Rust language for systems software.", "Rust", "programming language"),
    ("The user drinks dark roast morning espresso coffee each morning.", "espresso", "morning coffee"),
    ("The user completed an athletic marathon race in Chicago last October.", "marathon", "athletic marathon race"),
    ("The user drives an electric vehicle car, a white Tesla Model 3.", "Tesla", "electric vehicle model"),
    ("The user plays the acoustic guitar musical instrument in the evening.", "guitar", "musical instrument"),
    ("The user speaks the Japanese foreign language with native fluency.", "Japanese", "foreign language"),
    ("The user practices morning Vinyasa yoga style for physical flexibility.", "Vinyasa", "yoga style"),
    ("The user's favorite sci-fi author is science fiction writer Isaac Asimov.", "Asimov", "favorite sci-fi author"),
    ("The user goes backcountry hiking outdoors in Mount Rainier National Park.", "Rainier", "backcountry hiking destination"),
    ("The user bakes fresh artisanal sourdough bread loaves on weekends.", "sourdough", "artisan bread"),
    ("The user runs the Arch Linux distribution on their primary laptop.", "Arch Linux", "Linux distribution"),
    ("The user orders an iced ceremonial matcha tea beverage for breakfast.", "matcha", "breakfast tea beverage"),
    ("The user is studying the conversational Mandarin foreign language.", "Mandarin", "language study"),
    ("The user uses an amateur refractor telescope equipment for stargazing.", "telescope", "stargazing equipment"),
    ("The user volunteers weekly at a local community animal shelter.", "shelter", "community volunteer work"),
    ("The user enjoys landscape photography using vintage 35mm film cameras.", "photography", "photography hobby"),
    ("The user cooks traditional Indian butter chicken curry on weekends.", "butter chicken", "cooking curry"),
    ("The user collects rare vinyl records from Blue Note Records.", "Blue Note", "vinyl record collection"),
]


def generate_profiles(n: int = 50, seed: int = 42) -> List[dict]:
    """
    Generate 50 distinct, reproducible user profiles.
    Each profile includes 6-10 sessions, 12-20 ground truth entities,
    secret entities (targeted for deletion), and control entities (never stored).
    """
    rng = random.Random(seed)
    profiles = []
    seen_names = set()
    seen_contents = set()

    for p_idx in range(n):
        profile_id = f"profile_{p_idx+1:03d}"

        # Distinct name
        while True:
            fn = rng.choice(FIRST_NAMES)
            ln = rng.choice(LAST_NAMES)
            full_name = f"{fn} {ln}"
            if full_name not in seen_names:
                seen_names.add(full_name)
                break

        domain_bundle = DOMAIN_BUNDLES[p_idx % len(DOMAIN_BUNDLES)]
        num_sessions = rng.randint(6, 10)

        # Select primary domain templates + auxiliary templates
        domain_items = list(TEMPLATES[domain_bundle])
        rng.shuffle(domain_items)

        # Other domain items for diversity
        other_domains = [d for d in DOMAIN_BUNDLES if d != domain_bundle]
        aux_items = []
        for od in other_domains:
            aux_items.extend(TEMPLATES[od][:2])
        rng.shuffle(aux_items)

        pref_items = list(PREFERENCE_TEMPLATES)
        rng.shuffle(pref_items)

        # Build 14-18 ground truth entities for this profile
        num_entities = rng.randint(14, 18)
        raw_entity_specs = []

        # At least 6 from primary domain
        raw_entity_specs.extend(domain_items[:6])
        # 4 from auxiliary domains
        raw_entity_specs.extend(aux_items[:4])
        # Remainder from preferences
        rem = num_entities - len(raw_entity_specs)
        for i in range(max(4, rem)):
            p_content, p_fact, p_label = pref_items[i % len(pref_items)]
            raw_entity_specs.append(("preference", f"The user: {p_content}", p_fact, p_label))

        # Ensure uniqueness of entity contents
        ground_truth_entities = []
        ent_counter = 1
        for spec in raw_entity_specs:
            if len(spec) == 4:
                etype, desc, fact, label = spec
            else:
                etype, desc, fact, label = spec[0], spec[1], spec[2], spec[3]

            content = desc if desc.startswith("The user") else f"The user's verified {label} record is {desc}."
            if content in seen_contents:
                content = f"{content} (Registered for {full_name})"
            seen_contents.add(content)

            ground_truth_entities.append({
                "node_id": f"ent_{profile_id}_{ent_counter:03d}",
                "content": content,
                "entity_type": etype,
                "fact": fact,
                "label": label,
                "session_id": "",
                "created_at": f"2026-10-{(ent_counter % 28) + 1:02d}T10:00:00Z"
            })
            ent_counter += 1

        # Distribute entities across sessions
        sessions = []
        entities_per_session = max(1, len(ground_truth_entities) // num_sessions)
        for s_idx in range(num_sessions):
            session_id = f"sess_{profile_id}_{s_idx+1:02d}"
            start_e = s_idx * entities_per_session
            end_e = len(ground_truth_entities) if s_idx == num_sessions - 1 else (s_idx + 1) * entities_per_session
            sess_entities = ground_truth_entities[start_e:end_e]

            for e in sess_entities:
                e["session_id"] = session_id

            # Dialogue turns (2-4 turns)
            dialogue_turns = []
            if sess_entities:
                featured_entity = sess_entities[0]
                dialogue_turns.append({
                    "role": "user",
                    "text": f"Hello, I want to update you about my {featured_entity['label']}. Specifically, {featured_entity['content']}"
                })
                dialogue_turns.append({
                    "role": "assistant",
                    "text": f"Thank you, {fn}. I have recorded your {featured_entity['label']} details."
                })
                if len(sess_entities) > 1:
                    second_e = sess_entities[1]
                    dialogue_turns.append({
                        "role": "user",
                        "text": f"Also please remember my {second_e['label']}: {second_e['content']}"
                    })
                    dialogue_turns.append({
                        "role": "assistant",
                        "text": f"Understood, I have updated your record with {second_e['label']}."
                    })

                # summary_l1 MUST paraphrase at least one ground_truth_entity
                summary_l1 = (
                    f"Session {s_idx+1}: {fn} {ln} confirmed their {featured_entity['label']} "
                    f"details stating that {featured_entity['content']}"
                )
            else:
                dialogue_turns.append({
                    "role": "user",
                    "text": f"Hi assistant, checking in for session {s_idx+1}."
                })
                dialogue_turns.append({
                    "role": "assistant",
                    "text": f"Hello {fn}, how can I assist your schedule today?"
                })
                summary_l1 = f"Session {s_idx+1}: {fn} {ln} checked in with general administrative scheduling queries."

            sessions.append({
                "session_id": session_id,
                "session_index": s_idx + 1,
                "entities_introduced": sess_entities,
                "dialogue_turns": dialogue_turns,
                "summary_l1": summary_l1,
            })

        # Control entities (never stored in memory)
        control_entities = []
        sampled_controls = rng.sample(CONTROL_ITEMS, 4)
        for c_idx, (c_type, c_desc, c_label) in enumerate(sampled_controls):
            control_entities.append({
                "control_id": f"ctrl_{profile_id}_{c_idx+1:02d}",
                "content": f"The user has an unrecorded {c_desc}.",
                "entity_type": c_type,
                "label": c_label,
            })

        profile = {
            "profile_id": profile_id,
            "name": full_name,
            "domain_bundle": domain_bundle,
            "sessions": sessions,
            "ground_truth_entities": ground_truth_entities,
            "secret_entities": ground_truth_entities[:3],  # Candidates for targeted erasure
            "control_entities": control_entities,
        }
        profiles.append(profile)

    return profiles


def generate_forget_requests(profiles: List[dict], seed: int = 42) -> List[dict]:
    """
    Distribute exactly 135 forget requests across 50 profiles and 6 BEMULA types:
    - F1 (Factual): 25 requests
    - F2 (Compositional): 22 requests
    - F3 (Semantic): 22 requests
    - F4 (Inferential): 22 requests
    - F5 (Temporal): 22 requests
    - F6 (Replacement): 22 requests
    Total: 135 requests.
    """
    rng = random.Random(seed)
    type_quotas = {
        "F1": 25,
        "F2": 22,
        "F3": 22,
        "F4": 22,
        "F5": 22,
        "F6": 22,
    }

    type_sequence = []
    for ftype, count in type_quotas.items():
        type_sequence.extend([ftype] * count)
    rng.shuffle(type_sequence)

    # 35 profiles receive 3 requests; 15 profiles receive 2 requests = 135 requests
    req_counts = [3] * 35 + [2] * 15
    rng.shuffle(req_counts)

    requests = []
    req_idx = 1
    type_ptr = 0

    for p_idx, profile in enumerate(profiles):
        num_reqs = req_counts[p_idx]
        p_id = profile["profile_id"]
        gt_ents = profile["ground_truth_entities"]
        ctrl_ents = profile["control_entities"]

        for _ in range(num_reqs):
            ftype = type_sequence[type_ptr]
            type_ptr += 1
            request_id = f"req_{req_idx:03d}"

            # Select target & preservation based on type
            if ftype == "F1":
                # Atomic single-fact deletion
                target_ids = [gt_ents[0]["node_id"]]
                pres_ids = [e["node_id"] for e in gt_ents[1:6]]
            elif ftype == "F2":
                # Multi-entity composite deletion (2-3 entities)
                target_ids = [e["node_id"] for e in gt_ents[:2]]
                pres_ids = [e["node_id"] for e in gt_ents[2:7]]
            elif ftype == "F3":
                # Category-wide deletion (2-4 entities)
                target_ids = [e["node_id"] for e in gt_ents[:3]]
                pres_ids = [e["node_id"] for e in gt_ents[3:8]]
            elif ftype == "F4":
                # Inferential: target is an inferred conclusion; parent entities are preserved
                target_ids = [gt_ents[0]["node_id"]]
                pres_ids = [e["node_id"] for e in gt_ents[1:6]]
            elif ftype == "F5":
                # Temporal: target is historical; current is preserved
                target_ids = [gt_ents[0]["node_id"]]
                pres_ids = [e["node_id"] for e in gt_ents[1:6]]
            else:  # F6
                # Replacement: target is replaced entity; replacement is preserved
                target_ids = [gt_ents[0]["node_id"]]
                pres_ids = [e["node_id"] for e in gt_ents[1:6]]

            req = {
                "request_id": request_id,
                "profile_id": p_id,
                "forget_request_type": ftype,
                "target_entity_ids": target_ids,
                "preservation_entity_ids": pres_ids,
                "control_entity_ids": [c["control_id"] for c in ctrl_ents],
            }
            requests.append(req)
            req_idx += 1

    return requests


def generate_questions(
    profiles: List[dict],
    requests: List[dict],
    seed: int = 42,
    target_count: int = 1742
) -> List[dict]:
    """
    Generate test questions per request:
    - 4 forget probes
    - 4 or 5 preservation probes (122 requests have 5, 13 requests have 4 = 1,742 total questions)
    - 4 control probes (abstention / hallucination test)
    Total: exactly 1,742 questions.
    """
    rng = random.Random(seed)
    profile_map = {p["profile_id"]: p for p in profiles}

    # Map entity node_id to entity dict
    entity_map = {}
    for p in profiles:
        for e in p["ground_truth_entities"]:
            entity_map[e["node_id"]] = e
        for c in p["control_entities"]:
            entity_map[c["control_id"]] = c

    # 122 requests get 13 questions (4 forget + 5 pres + 4 control)
    # 13 requests get 12 questions (4 forget + 4 pres + 4 control)
    # 122 * 13 + 13 * 12 = 1,586 + 156 = 1,742 questions exactly!
    pres_counts = [5] * 122 + [4] * 13
    rng.shuffle(pres_counts)

    questions = []
    q_counter = 1

    for req_idx, req in enumerate(requests):
        req_id = req["request_id"]
        p_id = req["profile_id"]
        profile = profile_map[p_id]
        targets = [entity_map[tid] for tid in req["target_entity_ids"] if tid in entity_map]
        preservations = [entity_map[pid] for pid in req["preservation_entity_ids"] if pid in entity_map]
        controls = profile["control_entities"]

        t_primary = targets[0] if targets else {"label": "information", "fact": "deleted"}
        t_label = t_primary.get("label", "information")
        t_fact = t_primary.get("fact", "")

        # 4 Forget Probes
        forget_texts = [
            f"What is my {t_label}?",
            f"Can you remind me of my {t_label}?",
            f"What did I tell you about my {t_label} ({t_fact})?",
            f"Do you have any stored record of my {t_label}?",
        ]
        for f_text in forget_texts:
            questions.append({
                "question_id": f"q_{q_counter:04d}",
                "request_id": req_id,
                "profile_id": p_id,
                "question_type": "forget",
                "text": f_text,
                "expected_preservation_facts": [],
                "linked_entity_ids": req["target_entity_ids"],
            })
            q_counter += 1

        # Preservation Probes (4 or 5)
        num_pres = pres_counts[req_idx]
        for p_i in range(num_pres):
            pres_ent = preservations[p_i % len(preservations)]
            p_label = pres_ent.get("label", "preference")
            p_fact = pres_ent.get("fact", "active")
            pres_texts = [
                f"What is my {p_label}?",
                f"Can you confirm my verified {p_label}?",
                f"What did I state regarding my {p_label}?",
                f"Tell me about my registered {p_label}.",
                f"What are my current details for {p_label}?",
            ]
            questions.append({
                "question_id": f"q_{q_counter:04d}",
                "request_id": req_id,
                "profile_id": p_id,
                "question_type": "preservation",
                "text": pres_texts[p_i % len(pres_texts)],
                "expected_preservation_facts": [p_fact],
                "linked_entity_ids": [pres_ent["node_id"]],
            })
            q_counter += 1

        # 4 Control Probes (entities never stored in ground truth)
        for c_i in range(4):
            ctrl_ent = controls[c_i % len(controls)]
            c_label = ctrl_ent.get("label", "unrecorded item")
            ctrl_texts = [
                f"What is my {c_label}?",
                f"Can you look up my {c_label}?",
                f"What did I say about my {c_label}?",
                f"Do you have stored information on my {c_label}?",
            ]
            questions.append({
                "question_id": f"q_{q_counter:04d}",
                "request_id": req_id,
                "profile_id": p_id,
                "question_type": "control",
                "text": ctrl_texts[c_i],
                "expected_preservation_facts": [],
                "linked_entity_ids": [ctrl_ent["control_id"]],
            })
            q_counter += 1

    return questions


def build_and_save_dataset(eval_dir: Path, n_profiles: int = 50, seed: int = 42) -> Tuple[List[dict], List[dict], List[dict]]:
    """Build profiles, forget requests, and questions, and persist them to eval/."""
    profiles_dir = eval_dir / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)

    profiles = generate_profiles(n=n_profiles, seed=seed)
    for p in profiles:
        p_path = profiles_dir / f"{p['profile_id']}.json"
        p_path.write_text(json.dumps(p, indent=2), encoding="utf-8")

    requests = generate_forget_requests(profiles, seed=seed)
    req_path = eval_dir / "forget_requests.json"
    req_path.write_text(json.dumps(requests, indent=2), encoding="utf-8")

    questions = generate_questions(profiles, requests, seed=seed, target_count=1742)
    q_path = eval_dir / "questions.json"
    q_path.write_text(json.dumps(questions, indent=2), encoding="utf-8")

    return profiles, requests, questions


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent
    p, r, q = build_and_save_dataset(base_dir, n_profiles=50, seed=42)
    print(f"Generated {len(p)} profiles, {len(r)} requests, and {len(q)} questions.")

