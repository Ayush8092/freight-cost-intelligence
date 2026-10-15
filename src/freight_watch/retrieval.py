"""Local text-similarity ranking for context notes."""
from __future__ import annotations

import calendar

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .notes import NoteCard


class NoteRetriever:
    """Rank note candidates; verdict.py remains responsible for evidence checks."""

    def __init__(self, cards: list[NoteCard]):
        self.cards = list(cards)
        self._vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        self._matrix = self._vectorizer.fit_transform([c.text for c in self.cards]) if self.cards else None

    def rank(self, route: str, week_start=None, vs_own: float | None = None,
             vs_peer: float | None = None) -> list[tuple[NoteCard, float]]:
        if not self.cards:
            return []

        terms = [route, "freight cost increase higher costs surcharge disruption"]
        if week_start is not None:
            terms.extend([week_start.strftime("%Y-%m-%d"), calendar.month_name[week_start.month]])
        if vs_own is not None:
            terms.append("own history increase" if vs_own > 0 else "own history decrease")
        if vs_peer is not None:
            terms.append("peer route premium" if vs_peer > 0 else "peer route lower cost")
        query = self._vectorizer.transform([" ".join(terms)])
        scores = cosine_similarity(query, self._matrix).ravel()
        ranked = [(card, round(float(score), 6)) for card, score in zip(self.cards, scores)]
        return sorted(ranked, key=lambda item: (-item[1], item[0].note_id))
