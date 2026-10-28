"""
Vérification de la réputation des liens auprès de listes publiques de sites
dangereux. Nécessite internet. Si une source est inaccessible, l'analyse
continue sans elle et l'interface l'indique clairement.

Sources :
  - Google Safe Browsing (clé API gratuite, variable GOOGLE_SAFE_BROWSING_KEY)
  - OpenPhish (flux public de sites de phishing, sans clé)
"""
import time
from urllib.parse import urlparse

import requests

TIMEOUT = 6
SB_ENDPOINT = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
OPENPHISH_FEED = "https://openphish.com/feed.txt"

_cache = {"t": 0.0, "urls": set(), "hosts": set()}


def _avec_schema(url: str) -> str:
    return url if url.lower().startswith(("http://", "https://")) else "http://" + url


def _host(url: str) -> str:
    return (urlparse(_avec_schema(url)).hostname or "").lower()


def verifier_safe_browsing(urls, api_key):
    """Retourne {url: type_de_menace} pour les liens signalés par Google."""
    body = {
        "client": {"clientId": "gounsgou", "clientVersion": "0.2"},
        "threatInfo": {
            "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING",
                            "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": _avec_schema(u)} for u in urls],
        },
    }
    r = requests.post(SB_ENDPOINT, params={"key": api_key}, json=body, timeout=TIMEOUT)
    r.raise_for_status()
    return {m["threat"]["url"]: m["threatType"] for m in r.json().get("matches", [])}


def _charger_openphish(ttl=3600):
    if time.time() - _cache["t"] < ttl and _cache["urls"]:
        return _cache
    r = requests.get(OPENPHISH_FEED, timeout=TIMEOUT)
    r.raise_for_status()
    urls = {l.strip().lower() for l in r.text.splitlines() if l.strip()}
    _cache.update(t=time.time(), urls=urls, hosts={_host(u) for u in urls})
    return _cache


def verifier_openphish(urls):
    """Retourne la liste des liens présents dans le flux OpenPhish."""
    data = _charger_openphish()
    hits = []
    for u in urls:
        if _avec_schema(u).lower() in data["urls"] or _host(u) in data["hosts"]:
            hits.append(u)
    return hits


LIBELLES = {
    "SOCIAL_ENGINEERING": "hameçonnage / ingénierie sociale",
    "MALWARE": "logiciel malveillant",
    "UNWANTED_SOFTWARE": "logiciel indésirable",
    "POTENTIALLY_HARMFUL_APPLICATION": "application potentiellement dangereuse",
}


def verifier_reputation(urls, api_key=None):
    """
    Retourne (raisons[(points, texte)], statuts[str]).
    `statuts` dit quelles sources ont réellement répondu.
    """
    raisons, statuts = [], []
    if not urls:
        return raisons, statuts

    if api_key:
        try:
            res = verifier_safe_browsing(urls, api_key)
            for u, menace in res.items():
                raisons.append((60, f"Google Safe Browsing signale ce lien ({LIBELLES.get(menace, menace)}) : {u}"))
            statuts.append("✅ Google Safe Browsing consulté")
        except Exception as e:
            statuts.append(f"⚠️ Google Safe Browsing indisponible ({type(e).__name__})")
    else:
        statuts.append("ℹ️ Google Safe Browsing non configuré (pas de clé API)")

    try:
        for u in verifier_openphish(urls):
            raisons.append((60, f"Ce lien figure dans la liste de phishing OpenPhish : {u}"))
        statuts.append("✅ OpenPhish consulté")
    except Exception as e:
        statuts.append(f"⚠️ OpenPhish indisponible ({type(e).__name__})")

    return raisons, statuts
