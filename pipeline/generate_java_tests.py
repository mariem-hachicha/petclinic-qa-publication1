"""Genere les tests Java (JUnit 5 + REST Assured) a partir des cas de test valides.

Entree  : testcases/testcases_v3/REQ-*.json (liste "testcases" = cas ACCEPTES par le controle)
Sortie  : src/test/java/org/springframework/samples/petclinic/api/generated/REQ_xxx_Test.java
          (une classe par exigence, un @Test par cas ; le dossier est entierement regenere)

Cette etape est DETERMINISTE : pas d'IA. Le meme JSON donne toujours le meme Java.
Chaque classe herite de ApiTestBase (demarrage de PetClinic, login, jeton JWT).

Usage :
  python pipeline\\generate_java_tests.py
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "testcases" / "testcases_v3"
PACKAGE = "org.springframework.samples.petclinic.api.generated"
OUT_DIR = ROOT / "src" / "test" / "java" / Path(*PACKAGE.split("."))

HEADER = """// FICHIER GENERE AUTOMATIQUEMENT par pipeline/generate_java_tests.py - NE PAS MODIFIER A LA MAIN.
// Source : {source}
// Exigence : {req_id} - {description}
package {package};

import static org.hamcrest.Matchers.*;

import org.hamcrest.Matcher;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.samples.petclinic.api.ApiTestBase;

@DisplayName({class_display})
@SuppressWarnings({{"rawtypes", "unchecked"}})
class {class_name} extends ApiTestBase {{
"""


def java_string(text):
    """Litteral de chaine Java sur (guillemets, antislash, accents echappes en \\uXXXX)."""
    return json.dumps(text, ensure_ascii=True)


def java_value(value):
    """Valeur JSON -> expression Java pour equalTo(...). Retourne None si non traduisible."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value}f"  # REST Assured lit les decimaux JSON comme des float
    if isinstance(value, str):
        return java_string(value)
    return None


def matcher(check):
    """Verification d'un cas -> matcher Hamcrest. Retourne None si non traduisible."""
    op, value = check["operator"], check.get("value")
    if op == "exists":
        return "notNullValue()"
    if op == "not_exists":
        return "nullValue()"
    if op == "equals":
        if value is None:
            return "nullValue()"
        v = java_value(value)
        return f"equalTo({v})" if v is not None else None
    if op == "contains":
        v = java_value(value)
        if v is None:
            return None
        # Fonctionne pour une chaine (containsString) comme pour une liste (hasItem).
        # (Matcher) : deux matchers de types differents dans un meme anyOf.
        return (f"anyOf((Matcher) hasItem({v}), (Matcher) containsString({v}))"
                if isinstance(value, str) else f"hasItem({v})")
    return None


def test_method(tc, untranslated):
    req, exp = tc["request"], tc["expected"]
    lines = [
        "",
        "    @Test",
        f"    @DisplayName({java_string(tc['id'] + ' ' + tc['title'])})",
        f"    void {tc['id'].lower().replace('-', '_')}() {{",
        f"        request({java_string(tc['user']) if tc['user'] else 'null'})",
    ]
    for name, val in req["query"].items():
        lines.append(f"            .queryParam({java_string(name)}, {java_string(val)})")
    if req["body_json"]:
        lines.append(f"            .body({java_string(req['body_json'])})")
    lines.append(f"        .when().{req['method'].lower()}({java_string(req['path'])})")
    lines.append(f"        .then().statusCode({exp['status']})")
    for check in exp["body_checks"]:
        m = matcher(check)
        if m is None:
            untranslated.append(f"{tc['id']} : {check}")
            lines.append(f"            // verification non traduite : {json.dumps(check, ensure_ascii=True)}")
        else:
            lines.append(f"            .body({java_string(check['path'])}, {m})")
    # Le point-virgule termine la derniere vraie instruction (pas un commentaire).
    last = max(i for i, line in enumerate(lines) if not line.strip().startswith("//"))
    lines[last] += ";"
    lines.append("    }")
    return lines


def main():
    parser = argparse.ArgumentParser(description="Generation des tests Java a partir des cas de test")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="dossier des REQ-*.json")
    args = parser.parse_args()

    files = sorted(Path(args.source).glob("REQ-*.json"))
    if not files:
        sys.exit(f"Aucun fichier REQ-*.json dans {args.source}")

    # Le dossier est entierement regenere : il reflete toujours exactement les JSON.
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("*.java"):
        old.unlink()

    classes = tests = 0
    untranslated = []
    for f in files:
        result = json.load(open(f, encoding="utf-8"))
        if not result["testcases"]:
            continue
        req_id = result["requirement_id"]
        class_name = req_id.replace("-", "_") + "_Test"
        lines = [HEADER.format(
            source=f.relative_to(ROOT).as_posix(),
            req_id=req_id,
            description=f"{len(result['testcases'])} cas generes par {result['model']} ({result['prompt']})",
            package=PACKAGE,
            class_display=java_string(req_id),
            class_name=class_name,
        ).rstrip("\n")]
        for tc in result["testcases"]:
            lines += test_method(tc, untranslated)
            tests += 1
        lines.append("}")
        (OUT_DIR / f"{class_name}.java").write_text("\n".join(lines) + "\n", encoding="utf-8")
        classes += 1

    print(f"{classes} classes, {tests} tests generes dans {OUT_DIR.relative_to(ROOT).as_posix()}")
    if untranslated:
        print(f"Verifications non traduites ({len(untranslated)}) :")
        for u in untranslated:
            print("  -", u)


if __name__ == "__main__":
    main()