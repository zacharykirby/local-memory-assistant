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