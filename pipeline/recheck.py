"""Reverifie les reponses brutes deja generees (raw/) avec les regles de controle ACTUELLES.

N'appelle PAS Gemini : ne consomme aucun quota.
Ne modifie aucun fichier : affiche seulement le resultat.

Usage :
  python pipeline\\recheck.py testcases_v2
"""
import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_testcases import OUT_ROOT, REQUIREMENTS_FILE, SCHEMA_FILE, check_testcases, load_json  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Reverification des cas deja generes")
    parser.add_argument("version", help="dossier dans testcases/, ex. testcases_v2")
    args = parser.parse_args()

    data = load_json(REQUIREMENTS_FILE)
    requirements = {r["id"]: r for r in data["requirements"]}
    validator = Draft202012Validator(load_json(SCHEMA_FILE))

    raw_dir = OUT_ROOT / args.version / "raw"
    files = sorted(raw_dir.glob("REQ-*.txt"))
    if not files:
        sys.exit(f"Aucune reponse brute dans {raw_dir}")

    total_generated = total_valid = 0
    for f in files:
        req_id = f.stem
        try:
            parsed = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"{req_id} : JSON illisible ({exc})")
            continue
        valid, problems = check_testcases(parsed, requirements[req_id], validator)
        generated = len(parsed) if isinstance(parsed, list) else 0
        total_generated += generated
        total_valid += len(valid)
        print(f"{req_id} : {len(valid)}/{generated} cas valides")
        for p in problems:
            print("   -", p)

    rate = 100 * total_valid / total_generated if total_generated else 0
    print(f"\nTotal avec les regles actuelles : {total_valid}/{total_generated} cas valides ({rate:.0f} %)")


if __name__ == "__main__":
    main()