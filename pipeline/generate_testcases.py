"""Genere des cas de test (JSON) a partir des exigences, avec Gemini.

Usage :
  python pipeline\\generate_testcases.py REQ-AUTH-01
  python pipeline\\generate_testcases.py REQ-AUTH-01 REQ-OWN-03 --prompt pipeline/prompts/testcases_v2.md
  python pipeline\\generate_testcases.py --all

Les resultats vont dans testcases/<nom du prompt>/ (ex. testcases/testcases_v2/).
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from google import genai
from google.genai import errors, types
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_FILE = ROOT / "requirements" / "requirements.json"
SCHEMA_FILE = ROOT / "pipeline" / "testcase_schema.json"
OUT_ROOT = ROOT / "testcases"
DEFAULT_MODEL = "gemini-3.5-flash"
PAUSE_SECONDS = 6            # palier gratuit : on espace les appels
TIMEOUT_MS = 120_000         # on abandonne un appel apres 2 minutes au lieu de bloquer
RETRY_DELAYS = [10, 30, 60]  # secondes d'attente avant chaque nouvel essai (503 / 429)


class DailyQuotaExceeded(Exception):
    """Quota quotidien du palier gratuit epuise : inutile de reessayer avant demain."""


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def call_gemini(client, model, prompt, config):
    """Appelle Gemini et reessaie si le serveur est surcharge (503) ou le quota par minute atteint (429).
    Si c'est le quota PAR JOUR qui est epuise, on s'arrete tout de suite."""
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            print(f"   serveur occupe, nouvel essai dans {delay} s ...", flush=True)
            time.sleep(delay)
        try:
            return client.models.generate_content(model=model, contents=prompt, config=config)
        except errors.APIError as exc:
            if exc.code == 429 and "PerDay" in str(exc):
                raise DailyQuotaExceeded(str(exc)) from exc
            # Autre erreur (cle invalide, modele inconnu...) ou dernier essai : on abandonne.
            if exc.code not in (429, 503) or attempt == len(RETRY_DELAYS):
                raise


def build_prompt(template, conventions, schema, requirement, all_requirements):
    """Remplace les marqueurs du prompt par le vrai contenu.
    Un marqueur absent du prompt (ex. {{RELATED}} dans le v1) est simplement ignore."""
    related = [
        {"id": r["id"], "description": r["description"], "expected_status": r["expected_status"]}
        for r in all_requirements
        if r["endpoint"] == requirement["endpoint"] and r["id"] != requirement["id"]
    ]
    related_text = json.dumps(related, ensure_ascii=False, indent=2) if related else "Aucune"
    return (template
            .replace("{{CONVENTIONS}}", json.dumps(conventions, ensure_ascii=False, indent=2))
            .replace("{{SCHEMA}}", json.dumps(schema, ensure_ascii=False, indent=2))
            .replace("{{REQUIREMENT}}", json.dumps(requirement, ensure_ascii=False, indent=2))
            .replace("{{EXPECTED_STATUS}}", str(requirement["expected_status"]))
            .replace("{{RELATED}}", related_text))


def path_regex(endpoint_path):
    """'/api/owners/{ownerId}' -> regex qui accepte '/api/owners/1'."""
    parts = re.split(r"\{[^}]+\}", endpoint_path)
    return re.compile("[^/]+".join(re.escape(p) for p in parts))


def check_testcases(data, requirement, validator):
    """Retourne (cas valides, erreurs). Controle le schema PUIS les regles du prompt."""
    if not isinstance(data, list):
        return [], ["la reponse n'est pas un tableau JSON"]
    method, endpoint_path = requirement["endpoint"].split(" ", 1)
    expected_path = path_regex(endpoint_path)
    prefix = "TC-" + requirement["id"][len("REQ-"):] + "-"
    valid, errors_found = [], []
    for i, tc in enumerate(data, start=1):
        problems = [e.message for e in validator.iter_errors(tc)]
        if not problems:  # schema OK -> on verifie les regles du prompt
            if tc["requirement_id"] != requirement["id"]:
                problems.append("requirement_id different de l'exigence")
            if not tc["id"].startswith(prefix):
                problems.append(f"id ne commence pas par {prefix}")
            if tc["request"]["method"] != method:
                problems.append(f"methode {tc['request']['method']} au lieu de {method}")
            if not expected_path.fullmatch(tc["request"]["path"]):
                problems.append(f"chemin {tc['request']['path']} ne correspond pas a {endpoint_path}")
            if tc["expected"]["status"] != requirement["expected_status"]:
                problems.append(f"status {tc['expected']['status']} au lieu de "
                                f"{requirement['expected_status']} (contrat)")
        if problems:
            errors_found.append(f"cas {i} : " + " ; ".join(problems))
        else:
            valid.append(tc)
    return valid, errors_found


def main():
    parser = argparse.ArgumentParser(description="Generation de cas de test avec Gemini")
    parser.add_argument("req_ids", nargs="*", help="ids d'exigences, ex. REQ-AUTH-01")
    parser.add_argument("--all", action="store_true", help="toutes les exigences")
    parser.add_argument("--prompt", default="pipeline/prompts/testcases_v2.md")
    args = parser.parse_args()

    data = load_json(REQUIREMENTS_FILE)
    requirements = {r["id"]: r for r in data["requirements"]}
    if args.all:
        ids = list(requirements)
    elif args.req_ids:
        ids = args.req_ids
    else:
        parser.error("indique au moins un id d'exigence, ou --all")
    unknown = [i for i in ids if i not in requirements]
    if unknown:
        sys.exit("Exigences inconnues : " + ", ".join(unknown))

    prompt_path = ROOT / args.prompt
    template = prompt_path.read_text(encoding="utf-8")
    out_dir = OUT_ROOT / prompt_path.stem          # ex. testcases/testcases_v2
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)
    (out_dir / "sent").mkdir(parents=True, exist_ok=True)

    schema = load_json(SCHEMA_FILE)
    validator = Draft202012Validator(schema)
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    client = genai.Client(http_options=types.HttpOptions(timeout=TIMEOUT_MS))
    config = types.GenerateContentConfig(response_mime_type="application/json")

    total_generated = total_valid = 0
    failed_calls = []
    print(f"Modele : {model} | Prompt : {args.prompt} | Sortie : {out_dir.relative_to(ROOT)}")

    for n, req_id in enumerate(ids, start=1):
        requirement = requirements[req_id]
        prompt = build_prompt(template, data["conventions"], schema, requirement, data["requirements"])
        (out_dir / "sent" / f"{req_id}.txt").write_text(
            prompt,
            encoding="utf-8"
        )
        print(f"[{n}/{len(ids)}] {req_id} ...", flush=True)
        try:
            response = call_gemini(client, model, prompt, config)
            raw = response.text or ""
        except DailyQuotaExceeded:
            print("   QUOTA QUOTIDIEN EPUISE : arret. Le quota se reinitialise chaque jour.")
            failed_calls.extend(ids[n - 1:])
            break
        except Exception as exc:
            print(f"   ECHEC de l'appel Gemini : {exc}")
            failed_calls.append(req_id)
            continue

        # La reponse brute est gardee telle quelle : preuve pour le journal des prompts.
        (out_dir / "raw" / f"{req_id}.txt").write_text(raw, encoding="utf-8")

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            parsed, valid, problems = None, [], [f"JSON illisible : {exc}"]
        else:
            valid, problems = check_testcases(parsed, requirement, validator)
        generated = len(parsed) if isinstance(parsed, list) else 0
        total_generated += generated
        total_valid += len(valid)

        result = {
            "requirement_id": req_id,
            "model": model,
            "model_version": getattr(response, "model_version", None),
            "prompt": args.prompt,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "generated": generated,
            "valid": len(valid),
            "errors": problems,
            "testcases": valid,
        }
        with open(out_dir / f"{req_id}.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"   {len(valid)}/{generated} cas valides")
        for p in problems:
            print("   -", p)
        if n < len(ids):
            time.sleep(PAUSE_SECONDS)

        # Historique des lancements du programme
    run = {
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model,
        "prompt": args.prompt,
        "requirements": ids,
        "generated": total_generated,
        "valid": total_valid,
        "failed_calls": failed_calls
    }

    with open(OUT_ROOT / "runs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(run, ensure_ascii=False) + "\n")        

    rate = 100 * total_valid / total_generated if total_generated else 0
    print(f"\nTotal : {total_valid}/{total_generated} cas valides ({rate:.0f} %)")
    if failed_calls:
        print(f"Appels echoues ({len(failed_calls)}) : {', '.join(failed_calls)}")
        print("Relance-les plus tard : python pipeline\\generate_testcases.py "
              + " ".join(failed_calls) + f" --prompt {args.prompt}")


if __name__ == "__main__":
    main()