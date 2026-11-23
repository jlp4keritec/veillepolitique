"""Conservation : allegement des extraits, purge du journal technique, compactage, taille mesuree."""

from datetime import timedelta

from app import maintenance, parametres
from tests.test_orchestrateur import _orch, paris


def test_allegement_garde_l_essentiel(base, conn):
    orch, _ = _orch(base, conn, paris(9))
    orch.cycle(paris(9))
    evts = conn.execute("SELECT COUNT(*) FROM evenements").fetchone()[0]
    notifs = conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
    conn.execute("INSERT INTO journal (horodatage, niveau, composant, message) VALUES ('2020-01-01T00:00:00Z','INFO','x','vieux')")
    conn.commit()
    # 13 mois plus tard
    plus_tard = paris(9) + timedelta(days=30 * 13)
    res = maintenance.alleger(conn, plus_tard)
    assert res["extraits"] == 8 and res["journal"] >= 1
    a = conn.execute("SELECT * FROM articles LIMIT 1").fetchone()
    assert a["texte_extrait"] == "" and a["allege"] == 1 and a["titre"] and a["url"].startswith("https://")
    assert conn.execute("SELECT COUNT(*) FROM evenements").fetchone()[0] == evts          # rien d'autre touche
    assert conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == notifs
    assert maintenance.alleger(conn, plus_tard)["extraits"] == 0                          # idempotent


def test_reglage_zero_jamais(base, conn):
    orch, _ = _orch(base, conn, paris(9))
    orch.cycle(paris(9))
    parametres.modifier(conn, "conservation_extraits_mois", 0)
    assert maintenance.alleger(conn, paris(9) + timedelta(days=3650))["extraits"] == 0


def test_tache_de_nuit_une_fois_et_compactage(base, conn):
    orch, _ = _orch(base, conn, paris(9))
    orch.cycle(paris(9))
    orch.horloge(paris(3, 40, jour=24))
    assert conn.execute("SELECT valeur FROM etat WHERE cle = 'dernier_entretien_le'").fetchone() is None
    orch.horloge(paris(3, 45, jour=24))
    conn.commit()
    assert conn.execute("SELECT valeur FROM etat WHERE cle = 'dernier_entretien_le'").fetchone()
    assert conn.execute("SELECT valeur FROM etat WHERE cle = 'dernier_compactage_le'").fetchone()   # 1er du mois
    assert maintenance.tache(conn, paris(4, 0, jour=24)) is None                                    # une fois par nuit
    b = maintenance.tache(conn, paris(3, 50, jour=25))
    assert b is not None and "compactage" not in b                                                  # deja fait ce mois


def test_taille_mesuree(base, conn):
    t = maintenance.taille(conn, base, paris(9))
    assert t["mo"] > 0 and t["articles"] == 0 and t["projection_an_mo"] is None
