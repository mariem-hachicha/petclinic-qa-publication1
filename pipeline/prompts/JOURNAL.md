# Journal des prompts : generation des cas de test

Modele demande : gemini-3.5-flash (Google redirige vers gemini-3.6-flash, cf. champ "model_version").
Controle automatique : schema pipeline/testcase_schema.json + regles (requirement_id, id, methode, chemin, statut du contrat).
Traces conservees pour chaque execution :
- testcases/<version>/sent/REQ-xxx.txt : prompt exact envoye a Gemini (marqueurs remplis)
- testcases/<version>/raw/REQ-xxx.txt  : reponse brute de Gemini
- testcases/<version>/REQ-xxx.json     : cas retenus apres controle + erreurs detectees
- testcases/runs.jsonl                 : historique des executions (date, modele, prompt, totaux)

## Synthese

| Version | Date       | Echantillon      | Cas valides     | Cas hors perimetre |
|---------|------------|------------------|-----------------|--------------------|
| v1      | 2026-11-10 | 10 exigences     | 20/24 (83 %)    | 4                  |
| v2      | 2026-11-15 | memes 10         | 26/26 (100 %)   | 0                  |

## v1 : pipeline/prompts/testcases_v1.md
- Date : 2026-11-10 (Salma)
- Echantillon : REQ-AUTH-02, SEC-01, OWN-01, PAG-01, PET-01, VIS-01, VET-01, SPE-01, TYP-01, USR-01
- Resultat : 20/24 cas valides (83 %)
- Probleme constate : 4 cas hors perimetre. Pour des exigences dont le contrat attend 200
  (PAG-01, SPE-01, USR-01), Gemini ajoute de lui-meme des cas 401 / 403 deja couverts
  par d'autres exigences -> doublons et tracabilite faussee.
- Cause supposee : regle "code de l'exigence" trop abstraite ; Gemini ne savait pas que
  ces cas existaient ailleurs.

## v2 : pipeline/prompts/testcases_v2.md
- Changement (un seul, pour mesurer son effet) :
  - section "Perimetre" placee AVANT les regles ;
  - code attendu ecrit en clair ({{EXPECTED_STATUS}}) ;
  - liste des autres exigences du meme endpoint ({{RELATED}}).
- Date : 2026-11-15 (Mariem)
- Premier essai : REQ-OWN-01 -> 3/3 cas valides, tous en 201.
- Mesure sur le meme echantillon que v1 (2026-11-15, trace dans testcases/runs.jsonl) :
  26/26 cas valides (100 %), 0 cas hors perimetre (v1 : 20/24, 83 %, 4 hors perimetre).
  Les 3 exigences fautives en v1 (PAG-01, SPE-01, USR-01) sont toutes correctes en v2.
- Limites de la comparaison :
  - une seule execution par version (Gemini n'est pas deterministe) ;
  - v1 n'enregistrait pas la version reelle du modele (champ model_version ajoute ensuite) ;
  - 100 % de forme valide ne prouve pas que les cas sont corrects (voir defauts restants).
- Defauts restants (relecture humaine) :
  - format des chemins de body_checks instable ("$.id" ici, "accessToken" chez Salma) ;
  - TC-OWN-01-02 etiquete "securite" alors que c'est une variante d'utilisateur autorise.
- Prochaine piste (v3) : imposer un format de chemin unique ; preciser quand utiliser "securite".