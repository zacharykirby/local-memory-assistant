# memory.py
import json
from pathlib import Path

FACTS_FILE = Path(__file__).parent.parent / "data" / "facts.json"

def load_facts():
    """Load facts from JSON file"""
    if not FACTS_FILE.exists():
        FACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(FACTS_FILE, 'w') as f:
            json.dump([], f)
        return []
    
    with open(FACTS_FILE, 'r') as f:
        return json.load(f)

def save_fact(fact):
    """Append a new fact to the facts file"""
    facts = load_facts()
    if fact not in facts:  # avoid duplicates
        facts.append(fact)
        with open(FACTS_FILE, 'w') as f:
            json.dump(facts, f, indent=2)
        return True
    return False

def retrieve_facts(query=None):
    """Retrieve facts, optionally filtered by query"""
    facts = load_facts()

    # Return all facts if no query or empty string
    if not query or query.strip() == "":
        return facts

    # Case-insensitive substring search with partial word matching
    query_lower = query.lower().strip()

    # Split query into words for more flexible matching
    query_words = query_lower.split()

    matching_facts = []
    for fact in facts:
        fact_lower = fact.lower()
        # Match if the full query is in the fact OR if any query word matches
        if query_lower in fact_lower or any(word in fact_lower for word in query_words):
            matching_facts.append(fact)

    return matching_facts