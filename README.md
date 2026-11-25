<img src="assets/logo.png" alt="Emblème de Kelvaroq" width="112">

# Kelvaroq

Projet privé de compatibilité Xbox Series X|S pour Windows x64, écrit en Rust avec un moteur CPU de référence pour la recherche. L’objectif est une scène jouable en **3840 × 2160 à 30 images rendues par seconde**, avec ses textures correctes et une cadence régulière sur NVIDIA et AMD.

**État sur la RTX 5080.** Le lanceur exécute le jeu avec notre code de rendu et une surface de présentation de 3840 × 2160 en profil Series X. Au démarrage, une fenêtre de 30 intervalles présente une médiane de 33,3 ms. Dans une séquence lourde du prologue, la médiane atteint 601 ms. La cadence cible et la fidélité de toutes les textures restent à atteindre. [Mesures du moteur natif](documentation.md#rendu-natif-de-kelvaroq-sur-le-pc-de-test)

## Lancer le paquet Windows

1. Extraire entièrement le ZIP Windows x64 dans un dossier.
2. Ouvrir **Kelvaroq.exe**. Choisir le dossier du jeu ou son exécutable. Le glisser-déposer de l’un ou l’autre sur Kelvaroq.exe fonctionne aussi.
3. Le jeu ouvre sa fenêtre de rendu et une console **Kelvaroq | Journal du jeu**. Le lanceur utilise le moteur natif fourni dans le ZIP.

Le moteur natif réutilise le chargeur, le son et les entrées de VIctory. Le crate Rust de Kelvaroq intervient dans la préparation des textures et la mesure de la cadence. Le paquet inclut également le moteur de référence et son interpréteur. Le dossier peut être déplacé en conservant ses fichiers ensemble. Pour traiter un dossier, le lanceur utilise l’exécutable Series déclaré dans `MicrosoftGame.config`. En l’absence de manifeste, il accepte le seul `.exe` du dossier. En cas de choix ambigu, sélectionner le fichier directement.

La présentation native du profil Series X utilise une surface de 3840 × 2160. La fenêtre est ajustée aux dimensions du bureau. Les passes intermédiaires du jeu peuvent utiliser d’autres résolutions.

## Construire sous Windows

Utiliser Rust stable pour la cible MSVC x64, les outils de compilation Visual Studio avec le SDK Windows et Python x64 3.11 ou ultérieur. Depuis la racine du dépôt, dans PowerShell :

```powershell
cargo build --release --locked
python scripts/build_native.py
python -m venv .venv
.\.venv\Scripts\python -m pip install -e './research[dev]'
git config core.hooksPath .githooks
```

Le constructeur natif récupère la révision épinglée, applique les correctifs de rendu puis ajoute `native/kelvaroq-render` à la compilation. Avec un clone existant, utiliser `python scripts/build_native.py --source <clone>`. Les sauvegardes et le cache locaux de VIctory restent accessibles au moteur natif. Pour reconstruire le ZIP privé du prototype depuis Windows, exécuter `python scripts/package_windows.py`. Le script fournit les notices des composants tiers, vérifie leurs empreintes et teste l’archive décompressée hors du dépôt. Le résultat se trouve dans `target/dist/`. Le moteur de référence utilise Unicorn sous GPLv2. La notice et les sources amont correspondantes sont incluses. [Licence du moteur Unicorn](https://github.com/unicorn-engine/unicorn/blob/2.1.4/COPYING)

## Exécuter

`inspect` lit un fichier PE et donne son empreinte, son point d’entrée, ses sections et ses imports. Avec `--json`, il décrit aussi les adresses nécessaires au démarrage. `boot` exécute les instructions dans un espace mémoire invité. Remplacer le chemin d’exemple par celui du fichier local.

```powershell
$image = 'D:\images\exemple.exe'
.\target\release\kelvaroq inspect $image
.\target\release\kelvaroq boot $image --python .\.venv\Scripts\python.exe
.\target\release\kelvaroq play $image
.\target\release\kelvaroq gpu
```

`boot` fournit un rapport JSON et rend le code de sortie 0 si le point d’entrée revient, 2 si l’exécution invitée s’arrête avec un diagnostic, 1 pour une erreur d’outil ou de chargement. `play` utilise le moteur natif installé sous `native/victory.exe` à côté du CLI. `play --reference` ouvre le débogueur. Dans une compilation de développement sans backend natif, le CLI ouvre aussi le débogueur. Les deux commandes acceptent `--console series-s` et utilisent le profil Series X par défaut. Le manifeste choisit le SMT. Pour comparer les résultats de découverte CPU, `--host-topology` expose les enregistrements Windows du PC et `--processor-info <capture.bin>` rejoue des enregistrements x64 bruts. Conserver `kelvaroq_simd.dll` à côté du CLI. La sonde graphique indépendante accepte `gpu --adapter 0`.

## Vérifier les shaders sur la RTX 5080

Le banc de référence compile deux révisions précises du traducteur GFX10, exécute les programmes sur l’adaptateur matériel nommé et compare les valeurs relues. Il couvre huit cas d’extension de signe et deux programmes qui sélectionnent des textures différentes selon la voie. Sur la RTX 5080 de développement, les huit résultats entiers et les 64 échantillons de texture concordent.

```powershell
python scripts/check_shaders.py --adapter 'RTX 5080'
```

Git et Cargo sont nécessaires. Le premier lancement récupère les révisions, ensuite les objets Git sont conservés sous `target/shader-reference/`. L’option `--source` accepte aussi un clone local contenant les deux commits. Ce banc valide un traducteur externe sur des programmes contrôlés. En exécution native, le backend traduit aussi les shaders lors de la création des pipelines.

## Travailler sur le projet

- Pour construire, relire et tester une modification, suivre les [règles de contribution](CONTRIBUTING.md).
- Pour les choix d’architecture, les critères de compatibilité et le protocole de mesure, lire [documentation.md](documentation.md).
- Pour les observations sur le binaire, les adresses et l’arrêt reproductible, consulter le [carnet de décompilation](décompile.md).

Le dépôt contient le code, le logo et des programmes de test générés à partir de sources originales. Le fichier étudié est fourni localement par l’opérateur. Les conditions applicables au projet figurent dans [LICENSE](LICENSE).
