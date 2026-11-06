# Revue de la gestion automatique des skills

Cet audit conserve les observations initiales. Les validations supplémentaires et la CI effectivement exécutée figurent dans [le suivi](automatic-skills-followup.md) et [les résultats hébergés](automatic-skills-hosted-ci.json).

Audit initial : arbre propre, commit `85b9bd6`. Travail sur la branche `feat/automatic-task-skills`, sans publication de release ni déplacement de tag. L'analyse a confirmé le wrapper, les adaptateurs de manifestes/workspaces, les filtres de versions, les téléchargements GitHub, le verrouillage, les transactions récupérables et les désinstallations réversibles. Les principales lacunes étaient l'absence d'inventaire local avant recherche, de décision par tâche et d'intégration par demande ; les consignes générées interdisaient encore les installations implicites.

Le plan suivi : réutilisation locale et cache partagé ; protocole de décision validé ; intégration lancement/reprise/demande ; preuves déterministes, réseau et agent séparées ; revue des régressions. Le code réutilise les mécanismes de l'alpha. Aucune dépendance Python d'exécution, aucun autre service de modèle et aucune nouvelle clé API ne sont requis.

## Résultats observés

Environnement des essais natifs : Windows, Python 3.13.17, Codex CLI 0.166.0. Les essais avec inférence utilisent l'authentification Codex existante et le modèle `gpt-6.1-sol`. Les répertoires/profils/registre de test sont isolés ; les accès au registre sont injectés, jamais appliqués au profil Windows réel.

| Critère | Preuve reproductible |
|---|---|
| 1. Première visite automatique | Installation réelle dans un home temporaire puis lancement du vrai Codex par son wrapper, sans commande de sélection du dépôt : [démonstration](automatic-skills.json) |
| 2. Retour inchangé | Zéro appel de découverte/installation/analyse par modèle du gestionnaire ; verrou et empreintes/dates des fichiers conservés |
| 3. Skill local admissible | Guide Rust local sélectionné/coplié ; test interdisant toute recherche d'un équivalent distant |
| 4. Capacité externe | Guide Vercel téléchargé réellement, commit et SHA-256 enregistrés, installation et catalogue natif vérifiés : [réseau](automatic-skills-network.json), [consultation par l'agent](automatic-skills-live.json) |
| 5. Isolation monorepo | Catalogue natif et décision backend excluent les spécialités React ; les mentions de conservation d'un sibling n'en font plus une cible |
| 6. Changement frontend | Contenu et dates des ressources backend préservés ; assertions natives et démonstration existante conservées |
| 7. Nouvelle tâche | Même thread Codex repris pour corriger le frontend après Rust : nouveau hook observé, sélection remplacée, guide JavaScript consulté, validation Node et backend inchangé |
| 8. Dépôt inconnu | Socle utile, incertitudes explicites, zéro appel de modèle supplémentaire ; aucune classification de framework inventée |
| 9. Réseau/source invalides | Tests de refus et de panne existants, cache partagé utilisable hors ligne, licence/source/version incompatibles exclues avec repli local/embarqué |
| 10. Interruption/concurrence | Deux premières préparations réellement concurrentes ; processus interrompu avec `os._exit(73)` après une écriture, journal présent puis rejoué et verrou vérifié ; stress de 64 publications de cache avec six threads |
| 11. Désinstallation | Consignes préexistantes restaurées octet pour octet ; profils et ajouts PATH inversés dans le home de test ; skills préexistants, y compris une collision de rôle, conservés |
| 12. Vrai Codex | Catalogue réellement inspecté ; commandes de lecture des guides et marqueurs de consultation observés ; Cargo/Node valident indépendamment les comportements demandés |

Le guide externe observé provient de `vercel-labs/agent-skills`, commit `1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62`, licence déclarée MIT, SHA-256 des instructions `71ed7794962fa6e803ee83030517b5b93a9f70fbfeb431ec4535c5480a8d8355`. L'empreinte constate ce contenu épinglé ; elle ne certifie pas sa sécurité sémantique. La consultation distante est une observation distincte de sa présence au catalogue.

L'essai agent réussi corrige les en-têtes/trames Rust tronqués sans paniquer, conserve les trames valides/vides et les octets supplémentaires, puis corrige la gestion `null`/`undefined` et le trim du frontend dans la même session reprise. Les tests Cargo fournis par le harnais restent inchangés ; les assertions Node sont exécutées indépendamment du message final de l'agent.

Les trois tours observés ont rapporté respectivement 103 280, 207 181 et 104 345 tokens d'entrée, dont une grande part était mise en cache ; leurs détails restent dans le JSON. Ce sont des tâches synthétiques complètes et une consultation de guide, sans bras de comparaison. Ils ne démontrent aucune économie de tokens ou supériorité globale. Les comptes de guides activés et la latence de préparation sont enregistrés séparément de l'inférence. La tâche backend sélectionne neuf guides et zéro spécialité frontend. La couverture manquée ou inutile au-delà de ces fixtures n'a pas été mesurée sur un corpus utilisateur représentatif.

La première préparation réseau ordinaire, sans précharger un rôle ni le cache, a pris **272,76 secondes**, outils optionnels historiques inclus. Elle a sélectionné/installé le guide externe malgré 18 diagnostics de découverte rapportés et 149 requêtes de skills. Ce démarrage à froid reste coûteux ; les bornes de découverte de skills n'incluent pas le téléchargement/installation npm des outils existants. La préparation sans réseau et le retour sur les mêmes ressources sont vérifiés séparément. La suite complète locale a exécuté **307 tests, dont 5 ignorés, sans échec** ; les tests ignorés ne constituent pas des validations.

## Échecs conservés et corrections

[Essai 1](automatic-skills-attempt-1.json) : l'agent terminait Rust, mais la validation indépendante échouait et les ACL de sortie du sandbox Windows empêchaient le nettoyage. Le quota initial empêchait aussi le téléchargement complet du bundle React.

[Essai 2](automatic-skills-attempt-2.json) : correction/consultation Rust et validation indépendante réussies ; acquisition distante encore refusée par le quota. [Essai réseau intermédiaire](automatic-skills-network-attempt-1.json) : téléchargement possible après correction du transport `gh`, mais déclaration de licence du `SKILL.md` non reconnue. Ces résultats restent incomplets/échoués dans leurs fichiers.

[Essai 3](automatic-skills-attempt-3.json) : tâches Rust et frontend correctes et téléchargement distant réussi, mais la sélection frontend conservait Rust à cause de la phrase « préserver le backend ». Le guide React n'était pas consulté pour une modification purement JavaScript. La sélection privilégie maintenant les chemins ciblés ; le harnais mesure la consultation du guide JavaScript effectivement pertinent.

Les essais contrôlés avec inférence utilisent désormais `danger-full-access` pour leur fixture publique afin d'éviter les ACL de compilation du sandbox Windows. Le choix de sandbox de l'utilisateur n'est pas modifié par le produit. Les sorties brutes, y compris les échecs, sont conservées localement dans `reports/private/` et exclues des distributions et des rapports publics.

## Revue des régressions

Une revue indépendante en lecture seule a confirmé cinq problèmes : concurrence de l'éviction du cache, empreinte omise pour les cibles à la racine/relatives au workspace, dérive des manifestes pendant une demande de capacité, exclusion de skills préexistants du dépôt pour cette demande et multiplication du budget réseau entre scopes. Ils ont été corrigés avec des régressions ciblées. Les collisions avec les chemins de skills existants et l'exclusion globale des anciens `.codex/skills` ont également été reproduites puis corrigées. La fusion des hooks utilisateur et du gestionnaire a été contrôlée avec le vrai `hooks/list` : les deux sources restent présentes.

Les nouvelles préparations, demandes de capacité et rafraîchissements utilisent le verrou/journal existant. Les caches facultatifs restent utilisables en concurrence ; un échec de cache ne rend plus indisponibles des guides vérifiés. Les worktrees, déplacements du dépôt, changements de branche et modifications des fichiers ciblés disposent de tests de séparation/invalidation. Les requêtes externes restent composées de rôles/technologies, jamais du texte de tâche ou du code privé.

Reste à surveiller : faux positifs/négatifs de pertinence dans les dépôts réels, changements du protocole natif, mises à jour des versions amont, conflits entre consignes et consommation de ressources des outils optionnels historiques. Le premier téléchargement de ces outils peut être long ; son budget est distinct de la découverte de skills. Les bundles et états de tâche restent dans le cache utilisateur après désinstallation. Un arrêt brutal peut laisser un répertoire de staging abandonné ; la reprise reconstruit un verrou cohérent et la désinstallation préserve les fichiers non possédés.

## Limites et reproduction

Les nouveaux comportements natifs Linux/macOS et Python 3.11 n'ont pas été exécutés sur cette machine Windows. La CI correspondante est configurée ; sa définition ne constitue pas une exécution réussie. Avant d'annoncer ces combinaisons comme vérifiées, exécuter la matrice native et archiver ses résultats. Le binaire original et les clients Desktop/IDE/cloud contournant le wrapper ne bénéficient pas de l'intégration automatique. Une configuration globale interdisant les hooks peut conserver uniquement la préparation au lancement.

Le catalogue est configuré au lancement. Les hooks peuvent fournir des chemins de guides installés en cours de session, sans supposer qu'ils changent la configuration native instantanément. La consultation par chemin est le repli observé ; un lancement ultérieur reconstruit le catalogue et transmet la demande intacte. Aucun rechargement à chaud général n'est revendiqué.

Une présence au catalogue n'établit ni consultation ni application correcte. Les tâches et lectures observées satisfont ces états dans les fixtures ; elles ne prouvent pas l'obéissance d'un agent à toutes les instructions futures. La licence est une déclaration de provenance vérifiée dans le contenu épinglé, pas une expertise juridique. Les parsers de versions et de pertinence restent conservateurs et bornés.

Commandes :

```sh
python -m pip install -e .
python -m unittest discover -s tests -q
python -m ruff check src tests tools
python -m ruff format --check src tests tools
python tools/verify_automatic_skills.py
python tools/verify_automatic_skills.py --network --output reports/automatic-skills-network.json
python tools/verify_automatic_skills.py --agent --network --model gpt-6.1-sol --output reports/automatic-skills-live.json
python tools/demo_workspaces.py
python -m build --outdir dist-alpha
python tools/verify_native_install.py --codex PATH_TO_NATIVE_CODEX --expected-codex-version 0.166.0 --artifact dist-alpha/codex_repo_auto_bootstrap-1.4.0a1-py3-none-any.whl --artifact dist-alpha/codex_repo_auto_bootstrap-1.4.0a1.tar.gz
```

La vérification native des distributions est enregistrée dans [les résultats wheel/sdist](automatic-skills-artifacts.json). Les résultats ignorés ou indéterminés doivent rester visibles ; les bras sans `--agent` ou `--network` ne sont pas présentés comme les ayant exécutés.
