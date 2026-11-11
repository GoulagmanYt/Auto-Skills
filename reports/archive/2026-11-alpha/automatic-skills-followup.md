# Suivi des validations automatiques

Ce rapport complète [l'audit initial](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-review.md). Les essais natifs locaux utilisent Windows, Python 3.13.17, Codex 0.166.0 et l'authentification existante. La CI multiplateforme exécutée est enregistrée dans [les résultats hébergés](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-hosted-ci.json).

## Résultats observés

- [Session persistante réussie](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-interactive-retry.json) : un processus/thread natif, quatre tours Rust → frontend → acquisition/consultation d'une capacité locale supplémentaire → Rust. Quatre validations indépendantes réussies, aucun nouveau guide du workspace voisin consulté. La capacité ajoutée reste installée. Ce test configure explicitement app-server ; les clients app-server arbitraires restent hors intégration automatique, sans promesse de rechargement natif à chaud.
- [Échec conservé](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-interactive.json) : crédits épuisés, zéro tour natif terminé. Les hooks/sélections observés ne prouvent pas la réussite des tâches. Le compteur distingue maintenant tentatives et tours terminés.
- [Pertinence](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-measurement.md) : cinq extraits de manifestes publics épinglés, cinq scopes corrects, cinq retours avec cache réutilisé et artefacts préservés, sans réseau ni modèle pendant la préparation. Un rôle TypeScript est manqué dans Vue Reactivity ; deux guides static-analysis sont supplémentaires selon les annotations strictes. Ce ne sont pas des tâches réalisées dans cinq dépôts amont complets.
- [Tâches complètes](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-measurement-tasks.json) : trois tâches synthétiques, deux bras, six validations indépendantes réussies, une répétition et ordre alterné. Auto-Skills rapporte davantage de tokens d'entrée dans chacune des trois tâches. Les entrées en cache sont incluses dans ces comptes. Aucun gain de tokens ou de qualité n'est démontré.
- Démarrage ordinaire à froid : [avant](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-startup-before.json) **224,550 s**, [après](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-startup-after.json) **183,996 s**, mêmes 7 186 fichiers possédés dont 6 999 fichiers d'outils. Écart observé : 40,554 s (18,1 %), sur une paire de mesures avec variation réseau/machine possible. Les outils optionnels sont inclus ; environ trois minutes restent coûteuses.

L'optimisation supprime une seconde vérification complète immédiatement après celle de la transaction et remplace les résolutions répétées des ancêtres ordinaires par lstat. Les profils passent de deux à une vérification complète. Les empreintes restent vérifiées ; les liens/jonctions et points de réanalyse inconnus restent contrôlés. Quatre tests couvrent les redirections et le budget de vérification/résolution.

## Vérifications et risques

La suite complète locale a exécuté 319 tests sous Python 3.13 et 3.11, sans échec, dont cinq ignorés par exécution. Après revue, les quatre tests du vérificateur interactif et les cinq tests de mesure passent séparément, dont le nouveau test conservant une tentative interrompue comme indéterminée. La CI exécute la suite finale sur les trois systèmes et les distributions avec le catalogue du vrai Codex.

La revue indépendante a trouvé trois défauts du harnais, corrigés : perte des tentatives interrompues, délai RPC hors budget du tour, modèle affiché en dur. Aucun autre problème n'a été relevé dans l'optimisation du confinement et le retour du verrou déjà vérifié. Les risques restants comprennent la pertinence imparfaite, l'évolution du protocole, l'obéissance future de l'agent et le coût des outils optionnels. Les fixtures contrôlées ne garantissent pas toutes les tâches futures.

## Reproduction

```sh
python -m unittest discover -s tests -q
python tools/verify_interactive_skills.py --codex PATH_TO_NATIVE_CODEX --model gpt-6.1-sol
python tools/measure_automatic_skills.py
python tools/measure_automatic_skills.py --tasks --codex PATH_TO_NATIVE_CODEX --model gpt-6.1-sol
python tools/measure_startup.py --network
```

Les sorties brutes/profils restent dans `reports/private/`, hors Git et distributions. L'essai interactif s'arrête après un échec natif ; les tours non tentés sont distingués par le plan et les compteurs. Les mesures de tâches conservent toutes les lignes prévues, même en cas d'échec ou d'usage absent. Aucune release ni aucun tag ne fait partie de cette intégration.

## CI hébergée finale

[Exécution réussie](https://github.com/GoulagmanYt/Auto-Skills/actions/runs/42268009771) au commit 4cba53ee7e1925b701db3750694cab9193676d60: 320 tests dans chacune des six combinaisons Linux/macOS/Windows et Python 3.11/3.13, contrôles natifs Codex 0.166.0 des distributions/catalogues sur trois systèmes, build et matrice hors ligne. La découverte réseau optionnelle de CI est ignorée ; les essais réseau/inférence Windows restent distincts.

Les premiers passages macOS ont révélé un alias de fixture temporaire, corrigé sans affaiblir le refus des bundles liés. Les passages Windows ont révélé un timeout du validateur Rust dans le test de référence. Son budget de test est maintenant borné à 120 s ; les budgets des benchmarks mesurés restent inchangés. Le rejet de la fixture erronée doit désormais produire une empreinte du validateur exécuté, empêchant un timeout ou une compilation échouée de compter comme preuve de rejet sémantique. Ces échecs et leurs relances restent visibles.
