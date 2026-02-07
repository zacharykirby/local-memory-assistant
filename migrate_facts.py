#!/usr/bin/env python3
"""Migrate existing facts from facts.json to AI Memory/facts.md"""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from memory import save_fact, retrieve_facts

OLD_FACTS_FILE = Path(__file__).parent / "data" / "facts.json"


def migrate_facts():
    """Migrate facts from old JSON format to new Obsidian format"""
    print("=" * 60)
    print("Migrating Facts to Obsidian AI Memory")
    print("=" * 60)

    # Check if old facts file exists
    if not OLD_FACTS_FILE.exists():
        print("\n✓ No old facts.json file found - nothing to migrate")
        return

    # Load old facts
    print(f"\nReading facts from: {OLD_FACTS_FILE}")
    try:
        with open(OLD_FACTS_FILE, 'r') as f:
            old_facts = json.load(f)
    except Exception as e:
        print(f"✗ Error reading old facts: {e}")
        return

    if not old_facts:
        print("✓ No facts to migrate")
        return

    print(f"Found {len(old_facts)} fact(s) to migrate:")
    for i, fact in enumerate(old_facts, 1):
        print(f"  {i}. {fact}")

    # Check what's already in the new system
    existing_facts = retrieve_facts()
    print(f"\nCurrently in AI Memory: {len(existing_facts)} fact(s)")

    # Migrate facts
    print("\nMigrating facts...")
    migrated = 0
    skipped = 0

    for fact in old_facts:
        if save_fact(fact):
            print(f"  ✓ Migrated: {fact}")
            migrated += 1
        else:
            print(f"  ⊘ Skipped (duplicate): {fact}")
            skipped += 1

    # Summary
    print("\n" + "=" * 60)
    print(f"Migration Complete!")
    print(f"  - Migrated: {migrated} facts")
    print(f"  - Skipped: {skipped} facts (already existed)")
    print("=" * 60)

    # Verify
    print("\nVerifying migration...")
    all_facts = retrieve_facts()
    print(f"Total facts in AI Memory: {len(all_facts)}")
    for i, fact in enumerate(all_facts, 1):
        print(f"  {i}. {fact}")

    # Backup old file
    print(f"\n✓ Old facts.json backed up at: {OLD_FACTS_FILE}.bak")
    print("  (You can delete it once you verify the migration)")

    try:
        import shutil
        shutil.copy(OLD_FACTS_FILE, str(OLD_FACTS_FILE) + ".bak")
    except Exception as e:
        print(f"  ⚠ Could not create backup: {e}")

    print("\n✓ Facts are now stored in your Obsidian vault at:")
    print("  AI Memory/facts.md")


if __name__ == "__main__":
    migrate_facts()
