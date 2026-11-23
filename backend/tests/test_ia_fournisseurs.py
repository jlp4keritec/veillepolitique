"""IA multi-fournisseurs : IA locale (Ollama), relais, OpenRouter, double avis IA / regles, mesures."""

import json

import httpx

from app import parametres
from app.ia import ClientIA, proposer_classification, taux_accord
from tests.test_ia_recherche import _articles


def transport(routes, appels):
    """routes : {hote: fonction(req) -> httpx.Response}"""
    def handler(req):
        appels.append((req.url.host, req.url.path, json.loads(req.content) if req.content else None))
        return routes[req.url.host](req)
    return httpx.Client(transport=httpx.MockTransport(handler))


def ollama(texte, eval_count=50):
    return lambda req: httpx.Response(200, json={"message": {"role": "assistant", "content": texte},
                                                 "prompt_eval_count": 300, "eval_count": eval_count})


def claude(texte):
    return lambda req: httpx.Response(200, json={"content": [{"type": "text", "text": texte}],
                                                 "usage": {"input_tokens": 1000, "output_tokens": 200}})


def panne(req):
    raise httpx.ConnectError("bandit eteint")


LOCAL = "http://10.10.0.2:11434"


def test_ia_locale_gratuite_et_tracee(conn):
    ids = _articles(conn, ["Le gouvernement annonce une réforme des retraites"])
    prop = json.dumps([{"id": ids[0], "theme": "Retraites", "type_evenement": "réforme", "resume": "Résumé."}])
    appels = []
    ia = ClientIA("", transport({"10.10.0.2": ollama(prop)}, appels), local_url=LOCAL)
    assert proposer_classification(conn, ia) == 1
    assert appels[0][1] == "/api/chat" and appels[0][2]["model"] == "ministral-3:3b"
    assert "DONNEES NON FIABLES" in appels[0][2]["messages"][0]["content"]       # meme garde-fou
    c = conn.execute("SELECT * FROM couts").fetchone()
    assert c["fournisseur"] == "local" and c["cout_eur"] == 0
    a = conn.execute("SELECT historique, classif_details FROM articles WHERE id = ?", (ids[0],)).fetchone()
    assert "local:ministral-3:3b" in a["historique"]
    assert json.loads(a["classif_details"])["ia"]["theme_avis"] == "accord"


def test_relais_local_en_panne_puis_claude(conn):
    ids = _articles(conn, ["Le gouvernement annonce une réforme des retraites"])
    prop = json.dumps([{"id": ids[0], "theme": "Retraites"}])
    appels = []
    ia = ClientIA("cle-test", transport({"10.10.0.2": panne, "api.anthropic.com": claude(prop)}, appels), local_url=LOCAL)
    assert proposer_classification(conn, ia) == 1
    assert [h for h, _p, _c in appels] == ["10.10.0.2", "api.anthropic.com"]
    assert ia.dernier["fournisseur"] == "anthropic"
    assert conn.execute("SELECT valeur FROM etat WHERE cle = 'ia_local_pause_jusqu'").fetchone()   # pause
    # pendant la pause, l'IA locale n'est plus essayee (pas de cycle ralenti)
    appels.clear()
    ia.appeler(conn, "synthese", "s", "c")
    assert [h for h, _p, _c in appels] == ["api.anthropic.com"]


def test_rien_ne_repond_regles_seules(conn):
    _articles(conn, ["Le gouvernement annonce une réforme des retraites"])
    ia = ClientIA("", transport({"10.10.0.2": panne}, []), local_url=LOCAL)
    assert proposer_classification(conn, ia) == 0
    assert ia.disponible(conn)[0] is False                      # en pause, pas d'autre fournisseur


def test_openrouter_et_routage_de_j(conn):
    parametres.modifier(conn, "ia_routage", {"classification": ["openrouter:mistralai/mistral-small"],
                                             "synthese": ["anthropic:"], "question": ["anthropic:"]})
    ids = _articles(conn, ["Le gouvernement annonce une réforme des retraites"])
    appels = []
    reponse = {"choices": [{"message": {"content": json.dumps([{"id": ids[0], "theme": "Retraites"}])}}],
               "usage": {"prompt_tokens": 1000, "completion_tokens": 100}}
    ia = ClientIA("", transport({"openrouter.ai": lambda r: httpx.Response(200, json=reponse)}, appels),
                  openrouter_key="or-test", local_url=LOCAL)
    assert proposer_classification(conn, ia) == 1
    assert appels[0][2]["model"] == "mistralai/mistral-small"
    c = conn.execute("SELECT * FROM couts").fetchone()
    assert c["fournisseur"] == "openrouter" and c["cout_eur"] > 0


def test_double_avis_divergent_les_regles_tranchent(conn):
    ids = _articles(conn, ["Le gouvernement annonce une réforme des retraites"])
    theme_regles = conn.execute("SELECT theme FROM articles WHERE id = ?", (ids[0],)).fetchone()[0]
    prop = json.dumps([{"id": ids[0], "theme": "Défense", "type_evenement": "vote"}])
    ia = ClientIA("", transport({"10.10.0.2": ollama(prop)}, []), local_url=LOCAL)
    proposer_classification(conn, ia)
    a = conn.execute("SELECT theme, type_evenement, classif_details, historique FROM articles WHERE id = ?",
                     (ids[0],)).fetchone()
    assert a["theme"] == theme_regles and a["type_evenement"] == "réforme"          # regles conservees
    ia_avis = json.loads(a["classif_details"])["ia"]
    assert ia_avis["theme_avis"] == "divergent" and ia_avis["type_avis"] == "divergent"
    assert "avis divergent" in a["historique"]
    t = taux_accord(conn)["local:ministral-3:3b"]
    assert t["theme"] == {"n": 1, "accord": 0, "pct": 0}


def test_double_avis_complete_si_regles_vides(conn):
    ids = _articles(conn, ["Le gouvernement annonce une réforme des retraites"])
    conn.execute("UPDATE articles SET theme = NULL, themes = '[]', type_evenement = NULL WHERE id = ?", (ids[0],))
    prop = json.dumps([{"id": ids[0], "theme": "Retraites", "type_evenement": "réforme"}])
    proposer_classification(conn, ClientIA("", transport({"10.10.0.2": ollama(prop)}, []), local_url=LOCAL))
    a = conn.execute("SELECT theme, type_evenement FROM articles WHERE id = ?", (ids[0],)).fetchone()
    assert (a["theme"], a["type_evenement"]) == ("Retraites", "réforme")


def test_budget_ne_bloque_pas_l_ia_locale(conn):
    from app.util import to_iso, utcnow
    conn.execute("INSERT INTO couts (horodatage, agent, modele, tokens_in, tokens_out, cout_eur) "
                 "VALUES (?, 'test', 'm', 0, 0, 999.0)", (to_iso(utcnow()),))
    ia = ClientIA("cle-test", transport({"10.10.0.2": ollama("ok")}, []), local_url=LOCAL)
    assert ia.disponible(conn) == (True, "ok")
    assert ia.appeler(conn, "synthese", "s", "c") == "ok" and ia.dernier["fournisseur"] == "local"


def test_tester_et_lister(conn):
    appels = []
    routes = {"10.10.0.2": lambda r: httpx.Response(200, json={"models": [{"name": "ministral-3:3b"}]})
              if r.url.path == "/api/tags" else ollama('{"ok": true, "langue": "fr"}')(r)}
    ia = ClientIA("", transport(routes, appels), local_url=LOCAL)
    p = parametres.tous(conn)
    assert ia.lister_modeles(p, "local") == ["ministral-3:3b"]
    r = ia.tester(conn, "local", "ministral-3:3b")
    assert r["ok"] and r["duree_s"] >= 0
    assert ia.tester(conn, "anthropic", "")["ok"] is False                          # pas de cle


def test_budget_migre_vers_20(base, conn):
    from app.parametres import seed_parametres
    conn.execute("UPDATE parametres SET valeur = '50.0' WHERE cle = 'budget_mensuel_eur'")
    seed_parametres(conn)
    assert parametres.lire(conn, "budget_mensuel_eur") == 20.0 and parametres.lire(conn, "budget_x_eur") == 30.0
    conn.execute("UPDATE parametres SET valeur = '35' WHERE cle = 'budget_mensuel_eur'")   # choix de J : garde
    seed_parametres(conn)
    assert parametres.lire(conn, "budget_mensuel_eur") == 35
