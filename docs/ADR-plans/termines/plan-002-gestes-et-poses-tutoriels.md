# Plan 002 — Gestes et poses du personnage dans les tutoriels

ADR : [ADR-002](../../ADR/termines/002-gestes-et-poses-tutoriels.md) (Accepté le 2026-11-11). Un seul jeu à la fois
(`--wait-idle 3600`). Chaque étape : bancs unitaires, luacheck sur le mod ; test en jeu cité avec code de sortie,
ligne `summary` ou résultat, et dossier `runs\`.

## Tableau de bord

| # | Étape | Statut | Dépend de | Décisions ADR | Taille | Parallélisable avec |
|---|---|---|---|---|---|---|
| 1 | API `T.emote`, `T.emoteDone`, `T.sit`, `T.sitOn`, `T.crouch`, `T.getUp`, `T.seated` ; liste unique des gestes | Terminée (2026-11-11) | — | D01-D05 | S | — |
| 2 | Vérification en jeu et mode d'emploi (skill `pz-tutorial-video`) | Terminée (2026-11-11) | 1 | D01, D03 | S | — |

## Fiches

### Étape 1 — API dans `Tuto.lua`
Liste `PZDevKit.World.EMOTES` (lue par `Actions.lua`), fonctions de `Tuto.lua`, tests dans `tests/test_tuto_lua.py`.
**Sortie** : suite `python -m unittest discover -s tests` verte, `luacheck` sans avertissement.
**Preuves (2026-11-11)** : `python -m unittest discover -s tests` → `Ran 267 tests … OK` (7 nouveaux dans
`tests/test_tuto_lua.py`) ; `luacheck Contents` → `0 warnings / 0 errors in 13 files`. La liste des gestes vit dans
`World.lua` (`PZDevKit.World.EMOTES`), `Actions.lua` la lit.

### Étape 2 — En jeu et mode d'emploi
Partie ouverte par `pzdev sp <Projet> --no-quit`, puis `pzdev lua` : un geste, assis par terre, relevé, assis sur une
chaise, accroupi. Mode d'emploi ajouté à la skill `pz-tutorial-video`.
**Sortie** : résultats `pzdev lua` cités, `pzdev logs --errors` sans erreur nouvelle.
**Preuves (2026-11-11, confirmé en jeu, états lus par `pzdev lua`, animation non regardée à l'écran)** :
`pzdev sp SignalSmoke --no-quit` → code 0, `sp 41 PASS, 0 FAIL`, `SignalSmoke\runs\20261111-145720-sp-0ece3087e05b`.
`T.emote("thumbsup")` → `emote=thumbsup`, `emoteDone` faux puis vrai 4 s plus tard ; `T.emote("surrender", 3)` →
encore en cours à 1,5 s, fini à 4 s ; `T.sit()` → `seated=true ground=true` ; `T.getUp()` → `seated=false` ;
`T.crouch(true/false)` → `sneaking=true` puis `false` ; `T.sitOn` sur `furniture_seating_indoor_02_23` (2 cases) →
`seated=true furniture=true`, aucun FAIL, relevé ensuite. `pzdev logs --errors` → seule l'erreur vanilla connue
`handleMannequinZone`. Mode d'emploi ajouté à la skill `pz-tutorial-video`.
