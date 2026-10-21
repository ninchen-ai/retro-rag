
"""Technische Suchbegriff-Erweiterung für Retro-RAG."""

import re


TECHNICAL_SYNONYMS = {
    "piepton": ("beep codes", "beep"),
    "pieptöne": ("beep codes", "beep"),
    "signalton": ("beep codes", "beep"),
    "signaltöne": ("beep codes", "beep"),
}


def extract_technical_phrases(question):
    """Erkennt mehrteilige, großgeschriebene technische Ausdrücke."""

    pattern = (
        r"\b[A-Z][A-Za-z0-9+-]*"
        r"(?:\s+[A-Z][A-Za-z0-9+-]*){1,5}\b"
    )

    phrases = []
    seen = set()

    for match in re.finditer(pattern, question):
        # Deutsche Satzanfänge sind oft keine Fachbegriffe.
        if match.start() == 0:
            continue

        words = match.group().split()

        # Längere Phrasen und ihre Teilphrasen prüfen.
        # Beispiel: Award BIOS Beep Codes -> Beep Codes.
        for start in range(len(words) - 1):
            phrase = " ".join(words[start:])
            key = phrase.casefold()

            if key not in seen:
                seen.add(key)
                phrases.append(phrase)

    return phrases[:12]

def expand_search_terms(question):
    """Liefert zusätzliche technische Suchbegriffe zur Benutzerfrage."""

    words = set(
        re.findall(r"[^\W_]+", question.casefold(), re.UNICODE)
    )

    terms = []
    seen = set()

    for word in words:
        for term in TECHNICAL_SYNONYMS.get(word, ()):
            if term not in seen:
                terms.append(term)
                seen.add(term)

    for phrase in extract_technical_phrases(question):
        if phrase.casefold() not in {
            item.casefold() for item in terms
        }:
            terms.append(phrase)

    return terms
