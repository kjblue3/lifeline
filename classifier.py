"""Deterministic offline baseline. Replace with ExecuTorch inference later."""

def classify(text: str) -> dict:
    t = text.lower()
    categories = {
        'medical': ['injured', 'unconscious', 'bleeding', 'ambulance', 'heart attack'],
        'rescue': ['trapped', 'stranded', 'flood', 'collapsed', 'roof'],
        'fire': ['fire', 'smoke', 'burning'],
        'supplies': ['water', 'food', 'blanket', 'medicine', 'shelter'],
    }
    scores = {category: sum(word in t for word in words) for category, words in categories.items()}
    category = max(scores, key=scores.get) if max(scores.values()) else 'other'
    critical = ['unconscious', 'not breathing', 'trapped', 'heart attack', 'collapsed']
    high = ['injured', 'bleeding', 'fire', 'flood', 'stranded']
    urgency = 'critical' if any(w in t for w in critical) else 'high' if any(w in t for w in high) else 'medium'
    return {'category': category, 'urgency': urgency, 'confidence': None, 'engine': 'rules-baseline'}
