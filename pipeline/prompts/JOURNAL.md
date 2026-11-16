# Journal des prompts : generation des cas de test

Modele demande : gemini-3.5-flash (Google redirige vers gemini-3.6-flash, cf. champ "model_version").
Controle automatique (deterministe, sans appel a Gemini) : schema pipeline/testcase_schema.json
+ regles de check_testcases (requirement_id, id, methode, chemin, statut du contrat, coherence technique/statut).

Traces conservees pour chaque execution :
- testcases/<version>/sent/REQ-xxx.txt : prompt exact envoye a Gemini (marqueurs remplis)
- testcases/<version>/raw/REQ-xxx.txt  : reponse brute de Gemini (y compris les cas rejetes)
- testcases/<version>/REQ-xxx.json     : cas retenus apres controle + erreurs detectees
- testcases/runs.jsonl                 : historique des executions (date, modele, prompt, totaux)

## Synthese

| Version | Date       | Qui    | Exigences              | Controle initial | Controle strict (2026-11-16) |
|---------|------------|--------|------------------------|------------------|------------------------------|
| v1      | 2026-11-10 | Salma  | echantillon (10)       | 20/24 (83 %)     | non reverifie                |
| v2      | 2026-11-15 | Mariem | echantillon (10)       | 26/26 (100 %)    | 18/26 (69 %)                 |
| v2      | 2026-11-15 | Salma  | 16 nouvelles           | 49/49 (100 %)    | 42/49 (86 %)                 |
| v2      | total      |        | 26                     | 75/75 (100 %)    | 60/75 (80 %)                 |
| v3      | 2026-11-16 | Mariem | echantillon (10)       | -                | 27/27 (100 %)                |
| v3      | 2026-11-16 | Salma  | OWN-13 a OWN-22 (10)   | -                | 26/26 (100 %)                |

Echantillon de reference (identique pour toutes les versions) :
REQ-AUTH-02, SEC-01, OWN-01, PAG-01, PET-01, VIS-01, VET-01, SPE-01, TYP-01, USR-01

Jeu de donnees final : uniquement testcases/testcases_v3 (90 exigences, meme prompt, meme controle).
Les dossiers testcases_v1 et testcases_v2 sont conserves comme preuves de l'evolution du prompt.

## v1 : pipeline/prompts/testcases_v1.md
- Date : 2026-11-10 (Salma)
- Resultat sur l'echantillon : 20/24 cas valides (83 %)
- Probleme constate : 4 cas hors perimetre. Pour des exigences dont le contrat attend 200
  (PAG-01, SPE-01, USR-01), Gemini ajoute de lui-meme des cas 401 / 403 deja couverts
  par d'autres exigences -> doublons et tracabilite faussee.
- Cause supposee : regle "code de l'exigence" trop abstraite ; Gemini ne savait pas que
  ces cas existaient ailleurs.
- Incident : la relance du meme jour a ete bloquee par le quota gratuit (20 appels/jour/modele).
  -> le script s'arrete desormais proprement (DailyQuotaExceeded) au lieu de reessayer inutilement.

## v2 : pipeline/prompts/testcases_v2.md
- Changement (un seul theme : le perimetre) :
  - section "Perimetre" placee AVANT les regles ;
  - code attendu ecrit en clair ({{EXPECTED_STATUS}}) ;
  - liste des autres exigences du meme endpoint ({{RELATED}}).
- Echantillon (2026-11-15, Mariem) : 26/26 cas valides (100 %), 0 cas hors perimetre
  (v1 : 20/24, 83 %, 4 hors perimetre). Les 3 exigences fautives en v1 sont correctes en v2.
- Nouvelles exigences (2026-11-15, Salma) : AUTH-01, 03, 04, SEC-02 a 04, OWN-02 a 11
  -> 49/49 cas valides (100 %). Arret propre sur quota avant OWN-12 et OWN-13.
- Limites de la comparaison v1 / v2 :
  - une seule execution par version (Gemini n'est pas deterministe) ;
  - v1 n'enregistrait pas la version reelle du modele (champ model_version ajoute ensuite) ;
  - 100 % de forme valide ne prouve pas que les cas sont corrects (voir ci-dessous).
- Defauts trouves par relecture humaine :
  - format des chemins de body_checks instable ("$.id" dans certains cas, "accessToken" dans d'autres) ;
  - un cas "securite" attribue a un utilisateur autorise qui reussit (201).

## Controle renforce (2026-11-16)
- Changements du CONTROLE (pas du prompt) :
  - testcase_schema.json : "path" des body_checks doit suivre un format unique, sans "$"
    (ex. "id", "pets[0].name", "[0].id"), celui de REST Assured utilise pour les tests Java ;
  - check_testcases : "technique" doit correspondre au statut
    (nominal = 2xx, erreur = 4xx/5xx, securite = 401/403).
- Reverification des reponses v2 deja stockees (pipeline/recheck.py, sans appel a Gemini) :
  - echantillon (Mariem) : 18/26 (69 %) ; rejets : PET-01 (3/3), VET-01 (2/2), VIS-01 (3/3) ;
  - nouvelles exigences (Salma) : 42/49 (86 %) ; rejets : OWN-08 (4/4), OWN-11 (3/3) ;
  - total v2 : 60/75 (80 %).
  - Tous les rejets ont la meme cause : chemin ecrit avec "$." ("$.id", "$.telephone", "$[0].specialties"...).
  - Aucune incoherence technique/statut dans les reponses actuellement stockees.
- Constat : sans consigne, Gemini change de notation d'une exigence a l'autre -> justifie la regle 8 du v3.
- Non-determinisme observe : REQ-OWN-01 genere deux fois avec le meme prompt v2 ;
  1re reponse avec "$.id" et un cas "securite" mal etiquete, 2e reponse sans ces defauts.
- Defaut de tracabilite : la 2e generation a ecrase la 1re (raw/ et .json).
  A corriger : archiver l'ancienne reponse au lieu de l'ecraser.

## v3 : pipeline/prompts/testcases_v3.md
- Changement (un seul theme : la coherence des cas) :
  - regle 8 : format de "path" impose, SANS "$", avec des exemples ;
  - regles 9 et 10 : chaque "technique" liee au statut attendu ; un utilisateur autorise
    qui reussit n'est pas un cas "securite".
- Echantillon de reference (2026-11-16, Mariem, controle strict) :
  27/27 cas valides (100 %), contre 18/26 (69 %) pour le v2 avec le meme controle.
  Les 3 exigences rejetees en v2 pour le format "$." sont toutes valides en v3 :
  PET-01 (0/3 -> 3/3), VIS-01 (0/3 -> 3/3), VET-01 (0/2 -> 3/3).
- Nouvelles exigences (2026-11-16, Salma, controle strict) : OWN-13 a OWN-22 -> 26/26 (100 %).
  6 appels echoues pour des raisons reseau, sans lien avec le prompt :
  OWN-12 et OWN-23 (delai depasse), OWN-24 a OWN-27 (connexion internet coupee). A relancer.
- Limites : une seule execution par lot ; 100 % de forme valide ne prouve pas que chaque cas est juste.