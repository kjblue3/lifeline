"""Optional, offline ExecuTorch-assisted retrieval for LifeLine chat.

The ExecuTorch model provides a topic hint. SQLite performs the actual
document search. No medical decisions are made by the classifier.
"""
import re
from contextlib import closing

STOP = {
    "the", "and", "for", "are", "you", "what", "how", "should",
    "would", "could", "have", "has", "with", "from", "this",
    "that", "there", "their", "your", "friend", "someone",
    "please", "help", "need", "about", "while", "into",
}

TOPIC_WORDS = {
    "medical": ("medical", "injur", "bleed", "first aid", "health"),
    "fire": ("fire", "smoke", "burn"),
    "rescue": ("rescue", "emergency", "stranded", "trapped"),
    "supplies": ("supplies", "water", "shelter", "food"),
}


def words(text):
    return set(re.findall(r"[a-z]{3,}", (text or "").lower())) - STOP


def retrieve(question):
    # Import lazily. Failure must never prevent normal Qwen chat.
    from offline_ai.executorch_classifier import predict_category
    from medical_data.db import connect, search

    topic = predict_category(question)
    query_words = words(question)

    if not query_words:
        return {"topic": topic, "context": "", "matches": []}

    candidates = []

    with closing(connect()) as conn:
        for case in search(conn, question, limit=15):
            searchable = f"{case['title']} {case['aliases']}"
            overlap = len(query_words & words(searchable))
            if overlap == 0:
                continue

            has_summary = (
                case["content_status"] == "official_summary"
                and bool(case["summary"].strip())
            )

            if has_summary:
                body = (
                    f"OFFICIAL SUMMARY: {case['title']}\n"
                    f"{case['summary'][:650]}"
                )
            else:
                body = (
                    f"CATALOG METADATA ONLY: {case['title']}. "
                    "No medical instructions are stored for this entry."
                )

            hint = TOPIC_WORDS.get(topic, ())
            bonus = 0.25 if any(x in searchable.lower() for x in hint) else 0

            candidates.append((
                overlap + bonus + (2 if has_summary else 0),
                body + f"\nSource: {case['source_name']} | {case['source_url']}",
                case["title"],
            ))

        cards = conn.execute("""
            SELECT heading, description, response, source_name, source_url
            FROM emergency_cards
        """).fetchall()

        for card in cards:
            searchable = f"{card['heading']} {card['description']}"
            overlap = len(query_words & words(searchable))

            # Require more than one common word to avoid unrelated advice.
            if overlap < 2:
                continue

            body = (
                f"SOURCE-CHECKED DEMO NOTE: {card['heading']}\n"
                f"{card['description'][:300]}\n"
                f"{card['response'][:500]}\n"
                f"Source: {card['source_name']} | {card['source_url']}"
            )
            candidates.append((overlap + 3, body, card["heading"]))

    candidates.sort(key=lambda x: x[0], reverse=True)
    selected = candidates[:3]

    return {
        "topic": topic,
        "context": "\n\n".join(item[1] for item in selected)[:1800],
        "matches": [item[2] for item in selected],
    }
