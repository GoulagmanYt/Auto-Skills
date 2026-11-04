# Auto-Skills

**Un contexte de skills Codex explicable par workspace, maintenu quand le projet change.**

Version **1.3.0a1 alpha**, avec Codex CLI **0.166.0** comme référence native initiale. Auto-Skills analyse les manifestes, sélectionne un guide par rôle et workspace, verrouille les fichiers et réévalue les guides concernés par les changements de dépendances.

## Installation

Prérequis : Python 3.11+, Git et Codex CLI déjà installé. Depuis ce dépôt :

```powershell
# Windows
.\install.ps1
```

```sh
# Linux/macOS
sh install.sh
```

Ouvrir ensuite un nouveau terminal. L'exécutable Codex original est conservé.

```sh
codex-auto-bootstrap propose --repo ./projet --offline
codex-auto-bootstrap bootstrap --repo ./projet --offline
codex-auto-bootstrap context --repo ./projet --workspace backend
codex -C ./projet/backend
```

La prévisualisation affiche les guides actifs/exclus, raisons, provenance et estimation du catalogue. Un backend Rust ne reçoit pas les spécialités React/Vite de la racine. Un changement React conserve les guides Rust et les outils inchangés.

Le mode strict désactive pour le lancement les skills externes, plugins et serveurs MCP non explicitement conservés. Le mode `coexist`, dans `.codex/integrations.toml`, préserve les intégrations utilisateur ; le contexte externe n'est alors pas isolé. Le Codex original contourne le wrapper.

## Mise à jour et désinstallation

Relancer l'installeur depuis la version souhaitée pour mettre à jour le wrapper. Les manifestes modifiés déclenchent une mise à jour ciblée des guides.

```sh
codex-auto-bootstrap uninstall --repo ./projet --dry-run
codex-auto-bootstrap uninstall --repo ./projet
codex-auto-bootstrap uninstall
```

Les ajouts utilisateur indépendants sont conservés. Un fichier généré modifié ou une ancienne installation ambiguë peut nécessiter une résolution explicite. Ouvrir un nouveau terminal après retrait du wrapper.

Les mesures historiques de 18,87 % et 16,87 % concernent le contexte initial avant les nouvelles capacités Piano. Aucun gain global de facturation/cache n'en découle. Les guides distants restent des instructions non fiables par défaut ; les filtres et empreintes ne sont pas une certification de sécurité.

[Guide complet](README.md) · [Utilisation](docs/usage.md) · [Compatibilité](docs/compatibility.md) · [État réel de l'alpha](docs/public-alpha.md) · [Mesures](docs/benchmark.md) · [Contribuer](CONTRIBUTING.md)
