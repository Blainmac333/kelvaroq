# Règles d’ingénierie

## Responsabilités du code

| Emplacement | Responsabilité |
| --- | --- |
| `src/main.rs` | Commandes publiques, exécution du worker et codes de sortie. |
| `src/image.rs` | Validation du PE x64, contrôle des bornes, sections, imports, données TLS et empreinte. |
| `src/gpu.rs` | Interfaces Direct3D 12 et DXGI, soumission, fence et vérification du contenu GPU. |
| `research/kelvaroq_reference/memory.py` | Cartographie invitée, TLS, pile et contrôle des accès des services. |
| `research/kelvaroq_reference/cpu.py` | ABI x64, ordre des appels, reprise après initialiseur et budget d’exécution. |
| `research/kelvaroq_reference/kernel.py`, `crt.py`, `registry.py` | Sémantique des services émulés et état par processus invité. |
| `research/kelvaroq_reference/vector.py` | Opérations vectorielles de référence, largeurs et permissions mémoire. |
| `research/tests/` | Cas minimaux originaux qui exercent le comportement public et les contrats CPU. |

1. Un changement corrige un comportement observable. Indiquer le scénario initial, le résultat attendu et la preuve après correction. Une fonction dont la seule justification est de faire avancer le compteur d’instructions doit être revue.
2. Les noms et les types expriment l’unité et la portée. Distinguer RVA, adresse virtuelle invitée, décalage fichier et pointeur hôte. Une nouvelle conversion doit vérifier les bornes à l’endroit où elle se produit.
3. Une instruction, un format ou un import inconnu arrête la référence avec une cause. Tout chemin de succès décrit ses effets sur les registres, la mémoire, les ressources ou les erreurs. Les correctifs dépendant du nom du titre ou d’une adresse de ce titre sont exclus du moteur.
4. Le code Rust garde les appels `unsafe` au niveau de l’API native. Le relecteur vérifie les durées de vie, les tailles et la fin du travail GPU avant recyclage. Les tests de rendu relisent des valeurs attendues.
5. Une optimisation GPU conserve l’image attendue et les dépendances d’écriture. Joindre la scène, la résolution, le pilote et la dispersion des temps de trame. Un chiffre de FPS seul ne suffit pas pour accepter une optimisation.
6. Versionner le code source, les fixtures synthétiques et les résultats anonymisés. Garder les exécutables, captures de jeu, chemins personnels et données commerciales hors du dépôt. Pour le binaire de recherche, employer l’empreinte et les RVA.
7. À chaque clonage, activer `git config core.hooksPath .githooks`. Chaque commit porte la ligne `Co-authored-by: Moon AI (https://chat.realmoon.ai)`. Le hook l’ajoute et la CI contrôle les commits proposés.

## Vérifications avant intégration

Après l’installation du README, exécuter les commandes suivantes depuis la racine. La sonde GPU requiert du matériel Windows Direct3D 12 et se lance sur le PC de test pour tout changement de rendu.

```powershell
cargo fmt --all -- --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked
cargo build --release --locked
.\.venv\Scripts\ruff check research
.\.venv\Scripts\ruff format --check research
.\.venv\Scripts\python -m unittest discover -v -s research/tests
.\target\release\kelvaroq gpu
```
