# PZDevKit — documentation

> **DEV-ONLY. Ne jamais publier ce mod ni ce dossier sur le Workshop.**

Outil de développement local pour Project Zomboid 42.22 : un mod `batman_PZDevKit` et une CLI `pzdev` qui réunissent
les tests automatisés (ex-pz-autotest), le canal live et le tournage (ex-pz-tutorial), les scénarios (ex-PZPuppeteer) et
les productions (ex-PZDirector), sans agent Java.

| Document | Rôle |
|---|---|
| [architecture.md](architecture.md) | architecture cible, modules, sécurité, fonctions perdues |
| [specifications-techniques.md](specifications-techniques.md) | canal par fichiers, CLI, API Lua, correspondance ancien → nouveau |
| [ADR/](ADR/README.md) | décisions (ADR-001) et arbitrages ouverts |
| [ADR-plans/](ADR-plans/termines/plan-001-fusion-outils-pilotage.md) | plan par étapes et critères de sortie |
| [annexes/recherches/etude-etape-0.md](annexes/recherches/etude-etape-0.md) | inventaire des outils actuels, dépendances, diff 42.21 → 42.22 |
| [wiki/en/02-scenario-authoring.md](wiki/en/02-scenario-authoring.md), [wiki/en/03-campaign-workflow.md](wiki/en/03-campaign-workflow.md) | écrire un scénario, préparer une campagne (ex-PZPuppeteer) |
| [wiki/fr/01-tests-automatiques.md](wiki/fr/01-tests-automatiques.md) | mode d'emploi de `pzdev sp`, `server`, `mp`, `check` (ex-README de pz-autotest) |

À créer pendant l'implémentation, selon `docs/structure-documentaire.md` : `specifications-fonctionnelles.md`,
`ameliorations-et-idees.md`, le reste de `wiki/` (anglais et français).
