# Positionnement d'Auto-Skills

**Les bons skills, pour le bon workspace, dès le lancement de Codex.**

Auto-Skills s'adresse aux utilisateurs de Codex qui travaillent sur plusieurs dépôts ou sur un monorepo dont les packages n'ont pas tous les mêmes technologies et versions. Sa promesse est de maintenir une sélection locale, traçable et adaptée aux changements du projet.

## Quatre engagements

| Engagement | Critère d'acceptation | Preuve dans le dépôt |
|---|---|---|
| Bootstrap au lancement | Après installation du wrapper, un premier lancement crée le lock. Un lancement sans changement ne relance pas l'installation. Une modification de manifeste réévalue les slots affectés. | [Cycle de vie](../tests/test_lifecycle_upgrade.py), [wrapper et intégrité](../tests/test_bootstrap.py) |
| Compatibilité par workspace | React 18 et React 19 peuvent avoir des gagnants différents. Le lancement dans un workspace désactive les guides des voisins. Modifier un package conserve les fichiers et épingles de ses voisins inchangés. | [Intégration des workspaces](../tests/test_scoped_install_v12.py) |
| Un gagnant par slot fonctionnel | La sélection retient un seul candidat pour chaque couple `(workspace, slot)`. Les contraintes connues et outils requis sont vérifiés avant le score. Le rapport donne le motif de sélection ou de rejet. | [Sélection](../tests/test_selection_upgrade.py), [matrice publique](../reports/selection-matrix.json) |
| Outils et contexte adaptés | Un dépôt documentaire reçoit 6 skills et les outils locaux token-run/repo-map. Une application Python ne prévoit pas automatiquement Repomix ; une application JavaScript/TypeScript le prévoit. La CI bloque les nouvelles régressions définies par la matrice. | [Profils](../tests/test_policy_v12.py), [matrice](../reports/selection-matrix.md), [CI](../.github/workflows/test.yml) |

Un slot est un rôle précis : framework React, ORM, tests unitaires ou compression des sorties. L'unicité s'applique à ce rôle dans un workspace, pas à tout le monorepo.

## Démonstration reproductible

Après installation du projet avec `python -m pip install .` :

```sh
# Sélection distincte des guides React 18/19 et isolation au lancement.
python -m unittest tests.test_scoped_install_v12 -v

# Réutilisation des fichiers inchangés et profils d'outils adaptés.
python -m unittest tests.test_lifecycle_upgrade tests.test_policy_v12 -v

# Dépôts temporaires, vrais profileur et sélecteur, aucune dépendance réseau.
python tools/simulate_repositories.py --output reports/positioning-demo
```

La [matrice publique actuelle](../reports/selection-matrix.md) couvre 18 dépôts et 15 cas adversariaux. Elle utilise le catalogue intégré hors ligne ; les guides externes des tests adversariaux sont des fixtures et ne prouvent pas la disponibilité de guides équivalents sur GitHub. Les anciens audits détaillés sont archivés hors du dépôt public.

## Limites des promesses

- Le déclenchement automatique nécessite l'installation initiale du wrapper. L'exécutable Codex original permet de le contourner.
- Les contraintes absentes ou non interprétables ne constituent pas une compatibilité démontrée. La sélection conserve ses limites heuristiques.
- Un seul gagnant par slot ne garantit pas l'absence de contradictions entre tous les slots. La politique locale reste soumise aux instructions de priorité supérieure.
- Le profilage des manifestes évite de charger les fichiers d'implémentation. Les outils bornent certaines lectures et sorties ; aucun pourcentage d'économie de tokens n'est promis sans mesure.
- Le workflow CI est fourni. Une exécution locale réussie ne prouve pas qu'un job GitHub distant a été exécuté.

## Ligne éditoriale

Présenter d'abord le cycle lancement → profilage par workspace → sélection explicable → lock → mise à jour ciblée. Relier chaque promesse à un cas de test et à un résultat inspectable.

Le nombre de skills installés, les étoiles d'un dépôt et l'expression « zéro conflit » ne remplacent pas ces preuves. Les lacunes externes doivent rester visibles, y compris lorsque le catalogue intégré couvre les slots attendus.
