# ADR-002 — Gestes et poses du personnage dans les tutoriels

| Champ | Valeur |
|---|---|
| Identifiant | `ADR-002-GESTES-ET-POSES-TUTORIELS` |
| Date de création et de mise à jour | 2026-11-11 |
| Statut | Accepté (2026-11-11, par l'utilisateur : « Gestes + poses ») |
| Avancement | Terminé le 2026-11-11 (plan 002, étapes 1 et 2) |
| Décideur | l'utilisateur |
| Portée | `PZDevKit` : `client/PZDevKit/Tuto.lua`, `World.lua`, `Actions.lua`, skill `pz-tutorial-video` |
| Documents liés | [plan 002](../../ADR-plans/termines/plan-002-gestes-et-poses-tutoriels.md), [ADR-001](001-fusion-outils-pilotage.md) |
| Références | jeu installé 42.22 : `ISEmoteRadialMenu.lua` (identifiants et variantes), `ISSitOnGround.lua`, `ISJoystickButtonRadialMenu.lua` (`onToggleSit`), `ISWorldObjectContextMenu.lua` (`onRest`), `ISRestAction.lua` ; sources de référence locales : `IsoGameCharacter.playEmote`, `isSitting` |

## Contexte

Les vidéos tutoriels (`PZDevKit.Tuto`) ne savent faire jouer aucune animation au personnage. Seules les productions
(`PZDevKit.Production`, `scene:emote`) jouent les gestes vanilla. L'utilisateur veut, dans les tutoriels, des gestes
et des postures tenues.

## Décisions

- **D01 — Gestes vanilla.** `T.emote(id, hold)` joue un geste du menu radial vanilla (`IsoGameCharacter.playEmote`),
  identifiant exact, variantes comprises (`wavehi02`, `saluteformal`…). `hold` (0 à 60 s, facultatif) arrête un geste
  qui boucle. `T.emoteDone()` sert de condition `until_`. Un identifiant inconnu échoue tout de suite.
- **D02 — Une seule liste de gestes.** La liste des identifiants passe dans `World.lua` (`PZDevKit.World.EMOTES`) ;
  `Actions.lua` (productions) et `Tuto.lua` la lisent, sans copie.
- **D03 — Poses par les gestes vanilla du joueur.** S'asseoir par terre : l'événement de la touche « s'asseoir »
  (`EventSitOnGround`). S'asseoir sur un meuble : le « Se reposer » du menu contextuel (chemin vers le siège puis
  `ISRestAction` avec animations). S'accroupir : `setSneaking`. Se relever : le geste vanilla (`StopAllActionQueue` et
  `forceGetUp`). `T.seated()` lit `isSitting()`. Aucune animation forcée hors des mécanismes du jeu.
- **D04 — Pas de pose allongée.** Le jeu n'a pas de « s'allonger » hors du sommeil, qui fait sauter le temps : exclu.
- **D05 — Solo seulement.** Comme le reste de `Tuto`, ces commandes visent un tournage en solo.

Détails techniques appliqués par défaut (non soumis) : noms des fonctions, bornes de `hold`, messages en anglais.

## Conséquences

- Les scènes de tutoriel écrivent par exemple
  `T.step{ run = function() T.emote("thumbsup") end, until_ = T.emoteDone }`.
- Les productions gardent `scene:emote` inchangé.
