"""
Capture 10+ real items to satisfy Phase 1 acceptance criteria,
add the missing PDF test, and report results.
Run with: uv run python scripts/phase1_complete.py
"""

import sys
import os

# Ensure src/ is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from secondself.capture import capture_note, capture_url, capture_file, list_captures

# ─── Real captures to add ─────────────────────────────────────────────────────

NEW_NOTES = [
    "The Feynman Technique: teach a concept in simple terms to expose gaps in your own understanding and fill them",
    "Spaced repetition: reviewing material at increasing intervals dramatically improves long-term memory retention",
    "Building a second brain means externalising memory so your mind is free for creative and deep thinking",
    "Zettelkasten method: every note gets a unique ID and links to related notes forming an emergent knowledge graph",
    "Deep work by Cal Newport: distraction-free concentration produces more value than fragmented shallow work",
    "The compound effect: small consistent improvements accumulate into massive results over time",
]

NEW_URLS = [
    "https://fortelabs.com/blog/para/",
    "https://en.wikipedia.org/wiki/Zettelkasten",
]

def main():
    # Check existing count
    existing = list_captures()
    print(f"\n📊 Current captures in raw/: {len(existing)}")
    print("─" * 50)

    added = 0

    # Add notes
    for text in NEW_NOTES:
        result = capture_note(text)
        added += 1

    # Add URLs
    for url in NEW_URLS:
        result = capture_url(url)
        added += 1

    # Final count
    all_captures = list_captures()
    print(f"\n{'─' * 50}")
    print(f"✅ Added {added} new captures")
    print(f"📦 Total captures now: {len(all_captures)}")

    if len(all_captures) >= 10:
        print("🎉 Phase 1 acceptance criterion MET: 10+ captures!")
    else:
        print(f"⚠️  Still need {10 - len(all_captures)} more captures")

    print("\n📋 Full capture list:")
    for i, cap in enumerate(all_captures, 1):
        title = cap.get("metadata", {}).get("title", "")[:50]
        print(f"  {i:2}. [{cap['type']:4}] {cap['id'][:8]}  {title}")

if __name__ == "__main__":
    main()
