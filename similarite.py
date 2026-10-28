"""
Comparaison d'un message avec la base d'arnaques connues (scams_db.json).
Méthode : similarité cosinus sur trigrammes de caractères + mots,
sans dépendance externe. Les chiffres, liens et accents sont normalisés
pour que « 50000 FCFA » et « 75000 FCFA » soient vus comme équivalents.
"""
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path

DB_PATH = Path(__file__).parent / "scams_db.json"


def charger_base(path=DB_PATH):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def normaliser(texte: str) -> str:
    t = unicodedata.normalize("NFKD", texte.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"(https?://\S+|www\.\S+)", " url ", t)
    t = re.sub(r"\d+", "0", t)
    t = re.sub(r"[^a-z0 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _trigrammes(t: str) -> Counter:
    t = f" {t} "
    return Counter(t[i:i + 3] for i in range(len(t) - 2))


def _mots(t: str) -> Counter:
    return Counter(t.split())


def _cosinus(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    commun = set(a) & set(b)
    num = sum(a[k] * b[k] for k in commun)
    den = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return num / den if den else 0.0


def similarite(a: str, b: str) -> float:
    na, nb = normaliser(a), normaliser(b)
    return 0.5 * _cosinus(_trigrammes(na), _trigrammes(nb)) + \
           0.5 * _cosinus(_mots(na), _mots(nb))


def plus_proches(texte: str, base=None, top=3):
    """Retourne [(score, entree_base)] triés du plus au moins similaire."""
    base = base if base is not None else charger_base()
    res = [(similarite(texte, e["texte"]), e) for e in base]
    res.sort(key=lambda x: -x[0])
    return res[:top]


def points_similarite(texte: str, base=None):
    """
    Retourne (liste[(points, raison)], meilleure_correspondance | None).
    Seuils à calibrer avec de vrais messages.
    """
    proches = plus_proches(texte, base, top=1)
    if not proches:
        return [], None
    score, entree = proches[0]
    pct = round(score * 100)
    if score >= 0.60:
        pts = 45
    elif score >= 0.45:
        pts = 30
    elif score >= 0.35:
        pts = 15
    else:
        return [], None
    return [(pts, f"Ressemble à {pct}% à une arnaque connue : « {entree['titre']} ».")], (score, entree)
