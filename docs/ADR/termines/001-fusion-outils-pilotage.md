# ADR-001 — Fusion des outils de pilotage en un mod dev-only et une CLI

| Champ | Valeur |
|---|---|
| Identifiant | `ADR-001-FUSION-OUTILS-PILOTAGE` |
| Date de création et de mise à jour | 2026-11-10, mis à jour le 2026-11-11 |
| Statut | Accepté (2026-11-10, par l'utilisateur) |
| Avancement | Terminé le 2026-11-11 (plan 001, étapes 0 à 10) |
| Décideur | l'utilisateur |
| Portée | `.claude/tools/pz-autotest`, `.claude/tools/pz-tutorial`, `PZPuppeteer`, `PZDirector`, nouveau projet `PZDevKit` |
| Documents liés | [architecture](../../architecture.md), [spécifications techniques](../../specifications-techniques.md), [étude](../../annexes/recherches/etude-etape-0.md), [plan 001](../../ADR-plans/termines/plan-001-fusion-outils-pilotage.md) |
| Références | sources de référence 42.22 décompilées, locales (non publiées) (`api-diff-42.21-42.22.txt`, `SteamWorkshopItem.java`, `WorkshopSubmitScreen.lua`) |

## Contexte

Quatre outils se recouvrent : lanceur de tests (pz-autotest), canal live et tournage (pz-tutorial), moteur de
scénarios (PZPuppeteer), régie de tournage (PZDirector, avec l'agent Java ZombieBuddy). L'utilisateur a décidé de
retirer ZombieBuddy et de tout réunir en un mod dev-only plus une CLI.

## Décisions

- **D01 — Un mod, une CLI.** Un projet `Workshop\<Projet>` contient le mod `batman_<Projet>` (variante `42.21/`) et la
  CLI Python. Le pilote, le canal live, les aides monde, le moteur de scénarios, les productions et la bibliothèque de
  tournage deviennent des modules de ce mod.
- **D02 — Aucun agent Java.** ZombieBuddy, son correctif, son lanceur `-javaagent` et son client HTTP sont supprimés.
  Le pilotage externe passe par le canal par fichiers. Fonctions perdues listées dans l'architecture § 6.
- **D03 — Canal par fichiers unique.** `Lua\pzdev\cmd.lua` / `out.txt`, même chemin relatif en mode cache et en mode
  attaché, actif seulement en `-debug` (spécifications § 1).
- **D04 — Compatibilité stricte du lanceur.** Mêmes options, codes 0/1/2/3, `result.txt`, `summary.json`, `runs\` ;
  les dix `autotest.json` sont lus sans modification ; l'API Python `pzat.*` reste importable jusqu'à migration des
  scripts qui l'importent.
- **D05 — Barrière contre la publication.** Ni aperçu ni `workshop.txt`, fichier témoin
  `Contents\DEV-ONLY-DO-NOT-UPLOAD.txt` (refusé par `validateContents`), nom et description DEV-ONLY, refus dans
  `steam_workshop_publish.py`.
- **D06 — Une seule implémentation par aide monde.** `PZPuppet.Debug` et les aides monde de `tuto_lib` fusionnent dans
  `PZDevKit.World` ; `Tuto` garde seulement les gestes filmés.
- **D07 — Alias provisoires.** `pz_autotest.py`, `pzat.*`, `record.py`, `live.py`, `sheet.py`, les fichiers
  `pztuto_*`, les globales `PZPuppet`, `PZDirector`, `T` restent valables pendant au moins une étape après la bascule.
  Les alias Python et `pztuto_*` sont retirés à l'étape finale avec leurs tests. Les globales `PZPuppet`/`PZDirector`
  restent tant que des scénarios personnels ou Artemis les appellent.
  *Mise à jour 2026-11-11 (étape 10, décision de l'utilisateur)* : les globales `PZPuppet` et `PZDirector` sont
  retirées aussi (`Compat.lua` et son test supprimés) ; la campagne et les productions d'Artemis appellent
  `PZDevKit.Scenario`, `PZDevKit.World` et `PZDevKit.Production`. Les scénarios personnels ayant été archivés
  (étape 7), plus rien n'appelle les anciens noms. Contrats de données gardés : préfixes `[PZPuppet]`/`[PZDirector]`,
  chemins `Lua/PZPuppet/` (D09), clés `IGUI_PZDirector_*`.
- **D08 — Adaptateurs propres à un mod hors du mod générique.** `PZPuppet_MilitaryDrop.lua` part dans le projet
  MilitaryDrop (ou est abandonné s'il n'est plus utilisé) ; l'appel `LiveWire.Menu.onInspect` part dans les scènes
  LiveWire.
  *Mise à jour 2026-11-11 (étape 7)* : `PZPuppet_MilitaryDrop.lua` abandonné, son seul appelant est l'exemple 03 de
  PZPuppeteer (aucun dans MilitaryDrop ni dans les scénarios personnels) ; ses 4 tests partent avec lui. Il reste
  dans l'archive de PZPuppeteer (D14).
- **D09 — Chemins de scénarios inchangés.** `Lua\PZPuppet\scenarios`, `reports`, `last-report.txt`, `batch-ack.txt`
  sont conservés.
- **D10 — Corrections 42.22** (`getGameMode`, `addZombiesInOutfit`) intégrées pendant la fusion, chacune avec un test.
  *Mise à jour 2026-11-11* : `addZombiesInOutfit` n'est pas cassé, la 42.22 garde la surcharge à 13 paramètres
  (`LuaManager.java:8334`) ; aucune correction, un test vérifie l'appel à 13 paramètres. Ajoutées en cours de route :
  avertissement de conversion d'un monde 42.21 accepté sur la copie du cache (étape 3).

## Arbitrages rendus (2026-11-10, par l'utilisateur, un à un)

- **Q01 → D11 — Nom.** Projet `PZDevKit`, id `batman_PZDevKit`, CLI `pzdev`.
- **Q02 → D12 — Dépôt.** `cyberbobjr/PZDevKit` (privé à la décision ; *mise à jour 2026-11-11* : public sur
  décision de l'utilisateur, après retrait des références privées et historique repris en un seul commit), branche `main` ; aucun commit ni push sans demande explicite.
- **Q03 → D13 — Montage.** `assemble.py` devient la sous-commande `pzdev assemble`, déplacée sans changement de
  comportement.
- **Q04 → D14 — Anciens projets.** Archivés à l'étape finale, **après** migration des tests d'Opération Artemis :
  dépôt GitHub PZDirector marqué archivé, dossiers `PZPuppeteer` et `PZDirector` sortis de `Workshop` vers une archive
  locale (PZPuppeteer, sans dépôt, zippé), `tools/zombiebuddy` (318 Mo) supprimé.

Les étapes 2 et suivantes ne démarrent pas avant le passage de cet ADR à « Accepté ».
