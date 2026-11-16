"""Exporte les cas de test valides (testcases/testcases_v3/REQ-*.json) vers Kiwi TCMS.

Seule la liste "testcases" de chaque fichier est exportee (cas ACCEPTES par le controle).
Les dossiers raw/ et sent/ restent dans Git comme preuves : ils ne vont pas dans Kiwi.

Le script peut etre relance autant de fois que l'on veut : un cas deja present dans Kiwi
(meme identifiant TC-...) n'est pas recree.

Connexion (aucun secret dans le code) :
  KIWI_URL       (defaut : https://localhost:8443)
  KIWI_USER      (defaut : admin)
  KIWI_PASSWORD  (sinon le mot de passe est demande au clavier, sans s'afficher)

Usage :
  python pipeline\\export_kiwi.py --ping     # teste seulement la connexion
  python pipeline\\export_kiwi.py            # exporte testcases/testcases_v3
"""
import argparse
import getpass
import json
import os
import sys
from pathlib import Path

import requests
import urllib3

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_FILE = ROOT / "requirements" / "requirements.json"
DEFAULT_SOURCE = ROOT / "testcases" / "testcases_v3"

PRODUCT_NAME = "PetClinic REST"
CLASSIFICATION_NAME = "Projet de synthese"
VERSION_NAME = "v1"
PLAN_NAME = "PetClinic API - cas generes par Gemini (prompt v3)"
PLAN_TYPE_NAME = "Integration"
PRIORITY_BY_LEVEL = {"haute": "P1", "moyenne": "P2", "basse": "P3"}


class KiwiClient:
    """Client JSON-RPC minimal pour Kiwi TCMS (endpoint /json-rpc/)."""

    def __init__(self, url, verify_ssl):
        self.endpoint = url.rstrip("/") + "/json-rpc/"
        self.session = requests.Session()
        self.session.verify = verify_ssl
        self.next_id = 0

    def call(self, method, *params):
        self.next_id += 1
        payload = {"jsonrpc": "2.0", "method": method, "params": list(params), "id": self.next_id}
        response = self.session.post(self.endpoint, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        if data.get("error"):
            raise RuntimeError(f"{method} : {data['error'].get('message')}")
        return data["result"]

    def login(self, username, password):
        # Auth.login ouvre une session Django ; le cookie est garde par requests.Session.
        return self.call("Auth.login", username, password)


def get_or_create(kiwi, model, query, values=None):
    """Retourne le premier objet qui correspond a 'query', ou le cree avec 'values'."""
    found = kiwi.call(f"{model}.filter", query)
    if found:
        return found[0]
    return kiwi.call(f"{model}.create", values or query)


def case_text(tc):
    """Texte du cas dans Kiwi : preconditions, etapes et resultat attendu."""
    req = tc["request"]
    lines = ["## Preconditions"]
    lines += [f"- {p}" for p in tc["preconditions"]] or ["- aucune"]
    lines.append(f"- Utilisateur : {tc['user'] or 'aucun (requete sans authentification)'}")
    lines += ["", "## Etapes", f"1. Envoyer `{req['method']} {req['path']}`"]
    if req["query"]:
        lines.append(f"   - parametres : `{json.dumps(req['query'], ensure_ascii=False)}`")
    if req["body_json"]:
        lines.append(f"   - corps JSON : `{req['body_json']}`")
    lines += ["", "## Resultat attendu", f"- Statut HTTP : **{tc['expected']['status']}**"]
    for check in tc["expected"]["body_checks"]:
        value = f" `{json.dumps(check['value'], ensure_ascii=False)}`" if "value" in check else ""
        lines.append(f"- `{check['path']}` {check['operator']}{value}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Export des cas de test vers Kiwi TCMS")
    parser.add_argument("--ping", action="store_true", help="tester seulement la connexion")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="dossier des REQ-*.json")
    args = parser.parse_args()

    url = os.environ.get("KIWI_URL", "https://localhost:8443")
    # Certificat auto-signe de Kiwi en local : verification SSL desactivee seulement pour localhost.
    verify_ssl = not url.startswith("https://localhost")
    if not verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    username = os.environ.get("KIWI_USER", "admin")
    password = os.environ.get("KIWI_PASSWORD") or getpass.getpass(f"Mot de passe Kiwi pour {username} : ")

    kiwi = KiwiClient(url, verify_ssl)
    kiwi.login(username, password)
    print(f"Connecte a {url} en tant que {username}")
    if args.ping:
        print(f"Produits existants : {len(kiwi.call('Product.filter', {}))}")
        return

    # 1. Elements de base de Kiwi (crees une seule fois).
    classification = get_or_create(kiwi, "Classification", {"name": CLASSIFICATION_NAME})
    product = get_or_create(kiwi, "Product", {"name": PRODUCT_NAME},
                            {"name": PRODUCT_NAME, "classification": classification["id"],
                             "description": "API REST PetClinic (Spring Boot, JWT, 4 roles)"})
    version = get_or_create(kiwi, "Version", {"product": product["id"], "value": VERSION_NAME})
    plan_type = get_or_create(kiwi, "PlanType", {"name": PLAN_TYPE_NAME})
    plan = get_or_create(kiwi, "TestPlan", {"name": PLAN_NAME, "product": product["id"]},
                         {"name": PLAN_NAME, "product": product["id"], "product_version": version["id"],
                          "type": plan_type["id"],
                          "text": "Cas de test generes par Gemini a partir de requirements/requirements.json, "
                                  "puis valides par pipeline/generate_testcases.py."})
    statuses = kiwi.call("TestCaseStatus.filter", {"is_confirmed": True})
    if not statuses:
        sys.exit("Aucun statut de cas confirme trouve dans Kiwi.")
    case_status = statuses[0]
    priorities = {p["value"]: p["id"] for p in kiwi.call("Priority.filter", {})}

    # 2. Les cas de test.
    requirements = {r["id"]: r for r in json.load(open(REQUIREMENTS_FILE, encoding="utf-8"))["requirements"]}
    files = sorted(Path(args.source).glob("REQ-*.json"))
    if not files:
        sys.exit(f"Aucun fichier REQ-*.json dans {args.source}")

    created = skipped = 0
    for f in files:
        result = json.load(open(f, encoding="utf-8"))
        requirement = requirements[result["requirement_id"]]
        priority_id = priorities.get(PRIORITY_BY_LEVEL.get(requirement.get("priority"), "P3"))
        for tc in result["testcases"]:
            summary = f"{tc['id']} {tc['title']}"[:255]
            existing = kiwi.call("TestCase.filter", {"summary__startswith": tc["id"] + " "})
            if existing:
                case = existing[0]
                skipped += 1
            else:
                category = get_or_create(kiwi, "Category", {"name": tc["technique"], "product": product["id"]},
                                         {"name": tc["technique"], "product": product["id"],
                                          "description": "Technique de test (champ 'technique' du cas)"})
                case = kiwi.call("TestCase.create", {
                    "summary": summary,
                    "text": case_text(tc),
                    "requirement": tc["requirement_id"],
                    "product": product["id"],
                    "category": category["id"],
                    "priority": priority_id,
                    "case_status": case_status["id"],
                    "is_automated": False,
                    "notes": (f"Genere par {result['model']} ({result.get('model_version')}) "
                              f"avec {result['prompt']} le {result['generated_at']}."),
                })
                for tag in (tc["requirement_id"], tc["technique"], "gemini"):
                    kiwi.call("TestCase.add_tag", case["id"], tag)
                created += 1
            kiwi.call("TestPlan.add_case", plan["id"], case["id"])
        print(f"{result['requirement_id']} : {len(result['testcases'])} cas")

    print(f"\nPlan '{PLAN_NAME}' (id {plan['id']}) : {created} cas crees, {skipped} deja presents.")


if __name__ == "__main__":
    main()