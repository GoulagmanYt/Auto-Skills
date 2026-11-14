# Auto-Skills

**Des consignes Codex explicables pour chaque workspace, maintenues quand le projet change.**

Auto-Skills analyse les manifestes, sélectionne les skills pertinents, verrouille leur provenance et actualise les workspaces concernés. Un backend Rust conserve ses guides quand le frontend React change. Les dépôts inconnus reçoivent un socle portable avec leurs limites explicites.

**Alpha : 1.4.0a1.** La référence native vérifiée est Codex CLI **0.166.0**. [English](README.md) · [Utilisation](docs/usage.md) · [Couverture](docs/coverage.md) · [Compatibilité et preuves](docs/public-alpha.md)

## Installation

Prérequis : Python **3.11+**, Git et le Codex CLI original. Depuis un checkout de la version souhaitée :

```powershell
# Windows PowerShell
.\install.ps1
```

```sh
# Linux / macOS
sh install.sh
```

Ouvrir un nouveau terminal, puis utiliser Codex normalement :

```sh
codex -C ./projet "Corrige backend/src/lib.rs"
codex -C ./projet resume
```

L’installeur conserve l’exécutable original et enregistre ses modifications de PATH et de profil pour permettre leur annulation. La préparation utilise les skills locaux admissibles, les sources publiques autorisées et les guides intégrés. **Repomix attend une activation explicite** dans la politique globale. [Fonctionnement automatique et outils optionnels](docs/automatic-skills.md).

## Comprendre la sélection

Les installations gérées issues d’un checkout propre du dépôt officiel vérifient les mises à jour du bootstrap sur GitHub `main` une fois par jour, en arrière-plan au démarrage de Codex. La version vérifiée s’active au lancement suivant ; les sessions ouvertes conservent leur version. Voir les [commandes de mise à jour et de retour arrière](docs/usage.md#bootstrap-updates). Une installation existante nécessite une réinstallation manuelle pour recevoir ce mécanisme.

Dans une session interactive lancée avec Auto-Skills, **F9** ouvre le tableau de bord du dépôt. Les onglets **1 Skills**, **2 Plugins** et **3 MCP** affichent les fichiers installés, les lectures observées et les résultats des appels d’outils. **F9**, **Échap** ou **Q** revient à Codex en conservant la saisie. Un plugin sans appel observable reste **non vérifié**. [Détails et limites](docs/usage.md#keyboard-dashboard).

L’agent de développement identifie les besoins et délègue le choix des guides à **gpt-6-luna avec l’effort medium**, via le CLI Codex et son authentification existante. Ce sélecteur compare les candidats admissibles et enregistre son choix motivé, réutilisé pour une demande identique. Le premier lancement prépare un socle intégré rapide, avec une progression et la durée écoulée. [Fonctionnement détaillé](docs/ai-selection.md).

```sh
codex-auto-bootstrap propose --repo ./projet --offline
codex-auto-bootstrap context --repo ./projet
codex-auto-bootstrap check --repo ./projet
```

Les rapports expliquent les frontières des workspaces, les versions, la provenance, les exclusions et les incertitudes. Les déclarations personnalisées appartiennent à [auto-skills.toml](docs/configuration.md). [Diagnostic et récupération](docs/diagnostics.md).

## Intégrations

Le mode **strict**, activé par défaut, désactive pour ce lancement les skills externes, plugins et serveurs MCP non conservés explicitement. Pour préserver les intégrations utilisateur, ajouter dans `.codex/integrations.toml` :

```toml
[integrations]
mode = "coexist"
```

Des listes d’autorisation permettent aussi de conserver certaines intégrations en mode strict. Les configurations externes sont préservées. Le Codex original contourne le wrapper ; les clients Desktop/IDE restent hors intégration automatique du CLI. [Détails](docs/usage.md#integrations).

## Mise à jour et retrait

Relancer l’installeur depuis la version souhaitée. Les changements de manifestes déclenchent une actualisation ciblée.

Les mises à jour de Codex CLI restent gérées par Codex. Le wrapper conserve le chemin du lanceur natif et suit la version standalone courante, y compris pour les installations enregistrées par une ancienne version du wrapper.

```sh
codex-auto-bootstrap refresh --repo ./projet --offline
codex-auto-bootstrap uninstall --repo ./projet --dry-run
codex-auto-bootstrap uninstall --repo ./projet
codex-auto-bootstrap uninstall
```

Le retrait du dépôt et celui du wrapper sont distincts. Les ajouts indépendants sont conservés ; les conflits sont explicites. Ouvrir un nouveau terminal après retrait du wrapper. [Annulation](docs/diagnostics.md).

## Preuves et limites

Les tests couvrent l’isolation, l’intégrité, l’actualisation et la désinstallation. Les contrôles natifs des distributions utilisent la référence Codex épinglée. Les mesures et échecs historiques restent accessibles dans [le guide des preuves](docs/public-alpha.md). Les échantillons disponibles ne démontrent pas d’économie globale de tokens ni d’avantage général de performance.

Les guides distants restent des consignes non fiables par défaut. Les filtres et empreintes ne certifient pas leur innocuité. [Modèle de sécurité](docs/security-model.md).

## Développement

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
python -m tools.check_docs
```

Les tests isolent la configuration et le cache utilisateur et bloquent les connexions réseau directes. Les contrôles natifs et mesures avec inférence ont des commandes distinctes. [Contribution](CONTRIBUTING.md) · [Architecture](docs/architecture.md) · [Changelog](CHANGELOG.md) · [Publication](docs/release.md) · [Licence MIT](LICENSE)
