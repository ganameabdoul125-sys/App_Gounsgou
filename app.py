"""
GOUNSGOU - Prototype MVP (hackathon)
Lancer :  streamlit run app.py
"""
import os
import re
import sqlite3
from datetime import datetime
from urllib.parse import urlparse

import streamlit as st

import reputation
import similarite

st.set_page_config(page_title="GOUNSGOU", page_icon="🛡️", layout="centered")

st.markdown("""<style>
.stApp{background:radial-gradient(circle at 20% 0%,#0f4c9a 0%,#0a2a5e 40%,#061a3d 100%) fixed;color:#fff}
header[data-testid="stHeader"]{background:transparent}
.block-container{max-width:480px;padding:1rem 1rem 7rem}
h1,h2,h3,p,label,li,span,div{color:#fff}
.glass{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.18);
 backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);border-radius:22px;padding:14px 16px}
.hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}
.hdr h1{margin:0;font-size:1.7rem;font-weight:700}.hdr small{opacity:.75}
.circ{width:44px;height:44px;border-radius:50%;display:grid;place-items:center;
 background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.2);margin-left:8px;font-size:1.2rem}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:8px 0 16px}
.stat small{opacity:.75;display:block}.stat b{font-size:1.8rem}.stat i{font-style:normal;opacity:.7;font-size:.8rem}
.ring{width:96px;height:96px;border-radius:50%;margin:6px auto;display:grid;place-items:center;
 background:conic-gradient(var(--c) calc(var(--p)*1%),rgba(255,255,255,.12) 0)}
.ring span{width:74px;height:74px;border-radius:50%;background:#0b2a5c;display:grid;place-items:center;font-size:1.5rem;font-weight:700}
textarea,div[data-baseweb="select"]>div{background:rgba(255,255,255,.08)!important;color:#fff!important;
 border:1px solid rgba(255,255,255,.18)!important;border-radius:16px!important}
.stButton>button,.stFormSubmitButton>button{background:linear-gradient(135deg,#2f8cff,#1fb6ff);color:#fff;
 border:0;border-radius:999px;padding:.5rem 1.6rem;font-weight:600;box-shadow:0 6px 18px rgba(31,140,255,.4)}
[data-testid="stExpander"],[data-testid="stAlert"],[data-testid="stForm"]{background:rgba(255,255,255,.08);
 border:1px solid rgba(255,255,255,.18);border-radius:18px;backdrop-filter:blur(14px)}
[data-baseweb="tab-list"]{position:fixed;bottom:12px;left:50%;transform:translateX(-50%);width:min(456px,94vw);
 z-index:999;justify-content:space-around;background:rgba(10,30,70,.7);border:1px solid rgba(255,255,255,.2);
 backdrop-filter:blur(16px);border-radius:26px;padding:6px}
[data-baseweb="tab"]{background:transparent;border-radius:18px;padding:8px 6px;height:auto}
[data-baseweb="tab"][aria-selected="true"]{background:rgba(47,140,255,.35)}
[data-baseweb="tab-highlight"],[data-baseweb="tab-border"]{display:none}
</style>""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 1. BASE DE CONNAISSANCES (à enrichir avec des cas réels locaux)
# ---------------------------------------------------------------------------

# Marques ciblées par les arnaqueurs -> domaines officiels (À VÉRIFIER avant la démo)
MARQUES = {
    "orange": ["orange.bf", "orange.com", "orangemoney.com"],
    "moov": ["moov-africa.bf", "moov-africa.com"],
    "coris": ["corisbank.com", "coris.money"],
    "sank": ["sank.bf"],
    "wave": ["wave.com"],
    "onea": ["onea.bf"],
    "sonabel": ["sonabel.bf"],
}

TLD_SUSPECTS = {"xyz", "top", "click", "icu", "site", "online", "live", "buzz",
                "work", "tk", "ml", "ga", "cf", "gq", "info", "vip", "cyou"}

RACCOURCISSEURS = {"bit.ly", "tinyurl.com", "t.co", "cutt.ly", "is.gd",
                   "rebrand.ly", "shorturl.at", "tiny.cc", "wa.me"}

# (motif regex, points, explication)
INDICES_TEXTE = [
    (r"\b(urgent|immédiatement|immediatement|dans les \d+ ?(min|heures?)|"
     r"derni[eè]re chance|sous 24 ?h|maintenant)\b", 15,
     "Ton d'urgence : les escrocs cherchent à vous faire agir sans réfléchir."),
    (r"\b(code|pin|mot de passe|otp|code secret|code de confirmation)\b", 25,
     "Demande de code/PIN/mot de passe : aucun opérateur ne vous le demandera jamais."),
    (r"\b(vous avez gagn[ée]|f[ée]licitations|gagnant|tirage|concours|loterie|"
     r"cadeau|lot de)\b", 20,
     "Faux concours / gain inattendu : schéma classique d'arnaque."),
    (r"\b(d[ée]p[ôo]t (par erreur|erron[ée])|envoy[ée] par erreur|"
     r"rembours(er|ez) (moi|le)|renvoy(er|ez) (moi|l'argent))\b", 30,
     "Faux dépôt « par erreur » : l'arnaqueur vous demande de renvoyer de l'argent."),
    (r"\b(compte (bloqu[ée]|suspendu|d[ée]sactiv[ée])|votre compte sera|"
     r"v[ée]rifi(er|ez) votre (compte|identit[ée]))\b", 20,
     "Menace de blocage de compte : technique d'hameçonnage courante."),
    (r"\b(cliquez|clique) (ici|sur le lien)\b", 10,
     "Incitation à cliquer sur un lien."),
    (r"\b(je suis (de|du) (service|la banque)|service client|agent (orange|moov|coris))\b", 10,
     "Prétend venir d'un service officiel : à vérifier auprès du vrai service client."),
    (r"\b(frais de (dossier|livraison|d[ée]blocage)|payer .{0,20}pour recevoir)\b", 25,
     "Demande de paiement avant de recevoir un gain : arnaque aux frais d'avance."),
]

# Fiches d'arnaques (exemples génériques ; remplacer par des cas locaux documentés)
FICHES = [
    {
        "titre": "Faux dépôt « par erreur »",
        "icone": "💸",
        "comment": "Vous recevez un faux SMS de dépôt, puis un appel : « J'ai envoyé de "
                   "l'argent par erreur, pouvez-vous me le renvoyer ? »",
        "reflexes": [
            "Vérifiez votre solde réel via *#USSD# officiel, jamais via le SMS.",
            "Ne renvoyez rien : le dépôt n'a jamais eu lieu.",
            "Raccrochez et signalez le numéro à votre opérateur.",
        ],
    },
    {
        "titre": "Faux concours / tirage au sort",
        "icone": "🎁",
        "comment": "Un message annonce que vous avez gagné un téléphone ou une somme, "
                   "mais il faut payer des « frais » pour la recevoir.",
        "reflexes": [
            "Un vrai gain ne demande jamais de payer d'abord.",
            "Ne cliquez sur aucun lien, ne partagez aucune info personnelle.",
            "Supprimez le message et prévenez vos proches.",
        ],
    },
    {
        "titre": "Appel d'un faux agent du service client",
        "icone": "📞",
        "comment": "Une personne se présente comme agent de votre opérateur et "
                   "vous demande votre code secret pour « annuler une opération ».",
        "reflexes": [
            "Ne donnez JAMAIS votre code PIN, même à un « agent ».",
            "Raccrochez, puis rappelez le numéro officiel de l'opérateur.",
            "Changez votre code si vous l'avez communiqué.",
        ],
    },
    {
        "titre": "Faux lien de « vérification de compte »",
        "icone": "🔗",
        "comment": "Un SMS ou message WhatsApp prétend que votre compte va être "
                   "bloqué et contient un lien vers un faux site.",
        "reflexes": [
            "Ne cliquez pas : allez directement sur l'application officielle.",
            "Vérifiez le nom de domaine (orange.bf ≠ orange-verif.xyz).",
            "Collez le lien dans GOUNSGOU pour l'analyser.",
        ],
    },
    {
        "titre": "Usurpation de compte WhatsApp / Facebook",
        "icone": "👤",
        "comment": "Un « ami » vous écrit depuis un nouveau numéro et demande "
                   "un dépannage d'argent, ou vous demande un code reçu par SMS.",
        "reflexes": [
            "Appelez votre ami sur son ancien numéro pour confirmer.",
            "Ne partagez jamais le code à 6 chiffres reçu par SMS.",
            "Activez la validation en deux étapes (2FA).",
        ],
    },
]

KITS = {
    "WhatsApp : activer la validation en deux étapes": [
        "Ouvrez WhatsApp > Paramètres > Compte.",
        "Touchez « Validation en deux étapes » puis « Activer ».",
        "Créez un code à 6 chiffres que vous seul connaissez.",
        "Ajoutez une adresse e-mail de récupération.",
    ],
    "Facebook : sécuriser son compte": [
        "Paramètres > Centre de comptes > Mot de passe et sécurité.",
        "Activez l'authentification à deux facteurs.",
        "Vérifiez « Où vous êtes connecté » et déconnectez les appareils inconnus.",
        "Passez vos publications en « Amis » plutôt que « Public ».",
    ],
    "Mobile Money : bons réflexes": [
        "Changez votre code PIN régulièrement et ne le notez nulle part.",
        "Vérifiez toute transaction via le menu USSD officiel.",
        "Ne communiquez jamais un code reçu par SMS.",
        "En cas de fraude, contactez immédiatement votre opérateur.",
    ],
}

# ---------------------------------------------------------------------------
# 2. MOTEUR D'ANALYSE (transparent : chaque point de risque a une raison)
# ---------------------------------------------------------------------------

URL_RE = re.compile(r"(https?://[^\s]+|www\.[^\s]+|\b[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/[^\s]*)?)", re.I)


def extraire_urls(texte: str):
    urls = []
    for m in URL_RE.findall(texte):
        m = m.rstrip(".,;)")
        # écarte les faux positifs type "ok.merci"
        if "." in m and not re.fullmatch(r"\d+\.\d+", m):
            urls.append(m)
    return urls


def domaine_de(url: str) -> str:
    if not re.match(r"^https?://", url, re.I):
        url = "http://" + url
    return (urlparse(url).hostname or "").lower()


def domaine_racine(host: str) -> str:
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def analyser_url(url: str):
    """Retourne une liste de (points, raison)."""
    raisons = []
    host = domaine_de(url)
    racine = domaine_racine(host)
    tld = host.split(".")[-1] if "." in host else ""

    if url.lower().startswith("http://"):
        raisons.append((10, "Le lien n'est pas sécurisé (http au lieu de https)."))
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
        raisons.append((30, "Le lien utilise une adresse IP au lieu d'un nom de site."))
    if host in RACCOURCISSEURS or racine in RACCOURCISSEURS:
        raisons.append((15, "Lien raccourci : impossible de voir la vraie destination."))
    if tld in TLD_SUSPECTS:
        raisons.append((15, f"Extension de domaine « .{tld} » fréquemment utilisée pour des sites frauduleux."))
    if host.count("-") >= 2 or sum(c.isdigit() for c in host) >= 4:
        raisons.append((10, "Nom de domaine inhabituel (nombreux tirets ou chiffres)."))
    if host.count(".") >= 3:
        raisons.append((10, "Nombreux sous-domaines : technique pour imiter un site connu."))

    # Usurpation de marque
    for marque, officiels in MARQUES.items():
        if marque in host and racine not in officiels:
            raisons.append((40, f"Le lien imite « {marque.capitalize()} » mais n'est PAS son site officiel "
                                f"({', '.join(officiels)})."))
            break
    return raisons


def analyser(texte: str):
    texte = texte.strip()
    raisons = []
    bas = texte.lower()

    for motif, pts, expl in INDICES_TEXTE:
        if re.search(motif, bas, re.I):
            raisons.append((pts, expl))

    urls = extraire_urls(texte)
    for u in urls:
        for pts, expl in analyser_url(u):
            raisons.append((pts, f"[{domaine_de(u)}] {expl}"))

    # Numéro inconnu demandant un transfert
    if re.search(r"\b(envoy(er|ez)|transf[ée]r(er|ez))\b.{0,30}\b\d{3,}", bas):
        raisons.append((15, "Demande d'envoi d'argent à un montant précis."))

    score = min(100, sum(p for p, _ in raisons))
    if score < 25:
        niveau = "vert"
    elif score < 55:
        niveau = "orange"
    else:
        niveau = "rouge"
    return score, niveau, raisons, urls


def niveau_depuis_score(score):
    return "vert" if score < 25 else ("orange" if score < 55 else "rouge")


def cle_safe_browsing():
    cle = os.environ.get("GOOGLE_SAFE_BROWSING_KEY")
    if cle:
        return cle
    try:
        return st.secrets.get("GOOGLE_SAFE_BROWSING_KEY")
    except Exception:
        return None


@st.cache_data(ttl=600, show_spinner=False)
def reputation_en_cache(urls_tuple, cle):
    return reputation.verifier_reputation(list(urls_tuple), cle)


@st.cache_data(show_spinner=False)
def base_arnaques():
    return similarite.charger_base()


# ---------------------------------------------------------------------------
# 3. ALERTES COMMUNAUTAIRES (SQLite local)
# ---------------------------------------------------------------------------

def db():
    con = sqlite3.connect("alertes.db")
    con.execute("""CREATE TABLE IF NOT EXISTS alertes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, canal TEXT, description TEXT, statut TEXT DEFAULT 'en attente')""")
    return con


def ajouter_alerte(canal, desc):
    con = db()
    con.execute("INSERT INTO alertes(date, canal, description) VALUES (?,?,?)",
                (datetime.now().strftime("%d/%m/%Y %H:%M"), canal, desc))
    con.commit()
    con.close()


def lister_alertes():
    con = db()
    rows = con.execute("SELECT date, canal, description, statut FROM alertes ORDER BY id DESC LIMIT 20").fetchall()
    con.close()
    return rows


# ---------------------------------------------------------------------------
# 4. INTERFACE
# ---------------------------------------------------------------------------

st.markdown("""<div class="glass hdr"><div><h1>GOUNSGOU</h1>
<small>Vérifiez avant de cliquer 🛡️</small></div>
<div style="display:flex"><div class="circ">🔔</div><div class="circ">👤</div></div></div>""", unsafe_allow_html=True)

tab1, tab2, tab3, tab4 = st.tabs(["🔍 Vérifier", "📚 Guide", "🔐 Sécurité", "🚨 Alertes"])

# ---- Onglet 1 : VeriFact ---------------------------------------------------
with tab1:
    stats_ph = st.empty()
    st.subheader("Collez un SMS, un message WhatsApp ou un lien")
    exemples = {
        "— Choisir un exemple —": "",
        "Faux dépôt": "Vous avez reçu un dépôt de 50000 FCFA par erreur. Merci de me renvoyer l'argent urgent.",
        "Faux lien Orange": "URGENT: votre compte Orange Money sera bloqué dans 24h. Vérifiez ici http://orange-money-verif.xyz/login",
        "Faux concours": "Félicitations ! Vous avez gagné un téléphone. Payez les frais de livraison pour recevoir votre lot.",
        "Message normal": "Salut, on se voit demain à 18h pour le match ?",
    }
    choix = st.selectbox("Exemples pour tester", list(exemples.keys()))
    texte = st.text_area("Contenu à analyser", value=exemples[choix], height=140,
                         placeholder="Collez ici le message suspect...")

    en_ligne = st.toggle("Vérifier aussi les listes de sites dangereux (internet requis)", value=True)
    if st.button("Analyser", type="primary"):
        if not texte.strip():
            st.warning("Collez d'abord un message ou un lien.")
        else:
            score, niveau, raisons, urls = analyser(texte)
            raisons = list(raisons)

            # Similarité avec les arnaques connues
            pts_sim, proche = similarite.points_similarite(texte, base_arnaques())
            raisons += pts_sim

            # Réputation des liens (Safe Browsing / OpenPhish)
            statuts = []
            if en_ligne and urls:
                with st.spinner("Consultation des listes de sites dangereux..."):
                    r_rep, statuts = reputation_en_cache(tuple(urls), cle_safe_browsing())
                raisons += r_rep

            score = min(100, sum(p for p, _ in raisons))
            niveau = niveau_depuis_score(score)
            if niveau == "vert":
                st.success(f"🟢 RISQUE FAIBLE — score {score}/100")
                st.write("Aucun signal d'arnaque évident. Restez prudent : en cas de doute, "
                         "ne partagez jamais votre code PIN.")
            elif niveau == "orange":
                st.warning(f"🟠 SUSPECT — score {score}/100")
                st.write("Plusieurs signaux inquiétants. Ne cliquez pas et ne répondez pas "
                         "avant d'avoir vérifié auprès de la source officielle.")
            else:
                st.error(f"🔴 DANGER PROBABLE — score {score}/100")
                st.write("Ce message présente les caractéristiques d'une arnaque. "
                         "Ne cliquez pas, ne répondez pas, ne payez rien.")

            couleur = {"vert": "#34d399", "orange": "#fbbf24", "rouge": "#f87171"}[niveau]
            st.markdown(f'<div class="glass" style="text-align:center"><small>Niveau de risque</small>'
                        f'<div class="ring" style="--p:{score};--c:{couleur}"><span>{score}</span></div></div>',
                        unsafe_allow_html=True)
            st.session_state["n"] = st.session_state.get("n", 0) + 1

            if raisons:
                st.markdown("**Pourquoi ce verdict :**")
                for pts, r in sorted(raisons, key=lambda x: -x[0]):
                    st.markdown(f"- {r} *(+{pts})*")
            if urls:
                st.caption("Liens détectés : " + ", ".join(urls))
            for stt in statuts:
                st.caption(stt)
            if proche:
                sc, e = proche
                with st.expander(f"Arnaque connue la plus proche : {e['titre']} ({round(sc*100)}%)"):
                    st.write(f"**Canal :** {e['canal']}")
                    st.write(f"*« {e['texte']} »*")

            st.info("Ce score est une aide à la décision basée sur des critères visibles, "
                    "pas une preuve. En cas de doute, contactez votre opérateur.")

            fiche = (f"⚠️ ALERTE GOUNSGOU — niveau {niveau.upper()}\n"
                     f"Un message suspect circule. Ne cliquez pas, ne donnez jamais votre code PIN.\n"
                     f"Vérifiez sur GOUNSGOU avant d'agir.")
            st.text_area("Message à partager sur WhatsApp", fiche, height=110)

    stats_ph.markdown(f"""<div class="grid">
<div class="glass stat"><small>Analyses</small><b>{st.session_state.get("n", 0)}</b><i>cette session</i></div>
<div class="glass stat"><small>Arnaques connues</small><b>{len(base_arnaques())}</b><i>dans la base</i></div>
<div class="glass stat"><small>Signalements</small><b>{len(lister_alertes())}</b><i>communauté</i></div>
<div class="glass stat"><small>Fiches réflexes</small><b>{len(FICHES)}</b><i>à consulter</i></div></div>""",
        unsafe_allow_html=True)

# ---- Onglet 2 : CyberGuard -------------------------------------------------
with tab2:
    st.subheader("Guide anti-arnaque Mobile Money")
    for f in FICHES:
        with st.expander(f"{f['icone']} {f['titre']}"):
            st.markdown(f"**Comment ça marche :** {f['comment']}")
            st.markdown("**Vos réflexes :**")
            for r in f["reflexes"]:
                st.markdown(f"- ✅ {r}")

# ---- Onglet 3 : Kits -------------------------------------------------------
with tab3:
    st.subheader("Kits de sécurisation pas à pas")
    for titre, etapes in KITS.items():
        with st.expander(titre):
            for i, e in enumerate(etapes, 1):
                st.markdown(f"**{i}.** {e}")

# ---- Onglet 4 : Alertes ----------------------------------------------------
with tab4:
    st.subheader("Signaler une nouvelle arnaque")
    with st.form("form_alerte"):
        canal = st.selectbox("Canal", ["SMS", "Appel", "WhatsApp", "Facebook", "TikTok", "Autre"])
        desc = st.text_area("Décrivez l'arnaque (sans données personnelles)", height=100)
        ok = st.form_submit_button("Envoyer le signalement")
    if ok:
        if len(desc.strip()) < 15:
            st.warning("Décrivez un peu plus l'arnaque (15 caractères minimum).")
        else:
            ajouter_alerte(canal, desc.strip())
            st.success("Merci ! Votre signalement sera vérifié par un modérateur avant publication.")

    st.markdown("**Derniers signalements** *(en attente de modération)*")
    rows = lister_alertes()
    if not rows:
        st.caption("Aucun signalement pour le moment.")
    for d, c, ds, s in rows:
        st.markdown(f"- `{d}` · **{c}** · {ds} · _{s}_")

st.divider()
st.caption("GOUNSGOU — prototype hackathon - By GANAMESECNUM. Aide à la décision, ne remplace pas l'avis des autorités.")