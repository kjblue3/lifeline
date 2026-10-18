"""Optional trusted-reference context bridge for the normal Qwen chatbot.

MedicalLibrary performs strict trusted-reference selection.
ExecuTorch provides an optional ranking hint, never a safety gate.
No model or network access occurs on import.
"""

from medical_rag import MedicalLibrary

PREFERENCES = {
    "fire": ("Burns",),
    "rescue": ("Hypothermia", "Frostbite"),
    "supplies": ("Dehydration",),
}


def build_reference_context(question, *, predict=None, library=None):
    library = library if library is not None else MedicalLibrary()

    # This existing search already enforces provenance and relevance rules.
    rows = library.search(question, limit=5)

    topic = None
    if predict is not None:
        try:
            candidate = predict(question)
            if candidate in ("medical", "rescue", "fire", "supplies", "other"):
                topic = candidate
        except Exception:
            pass  # Optional classifier must never break retrieval.

    preferred = PREFERENCES.get(topic, ())
    ranked = sorted(
        enumerate(rows),
        key=lambda item: (
            0 if item[1]["title"] in preferred else 1,
            item[0],
        ),
    )

    selected = []
    excerpts = []

    for _, row in ranked:
        if len(selected) >= 2:
            break

        if row.get("content_status") != "official_summary":
            continue

        summary = row.get("summary", "").strip()
        if not summary:
            continue

        passage = (
            "Reference title: " + row["title"] + "\n"
            + "Source: " + row["source_name"] + "\n"
            + "URL: " + row["source_url"] + "\n"
            + "Original reference excerpt:\n" + summary
        )

        # Never truncate a medical passage mid-warning.
        if len("\n\n".join(excerpts + [passage])) > 7000:
            continue

        excerpts.append(passage)
        selected.append({
            "title": row["title"],
            "url": row["source_url"],
        })

    return {
        "executorch_topic": topic,
        "references": selected,
        "context": "\n\n".join(excerpts),
    }
