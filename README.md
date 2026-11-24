<img src="assets/logo.png" alt="Emblème de Kelvaroq" width="112">

# Kelvaroq

Projet privé de compatibilité Xbox Series X|S pour Windows x64, écrit en Rust avec un moteur CPU de référence pour la recherche. L’objectif est une scène jouable à 30 images rendues par seconde, avec ses textures correctes et une cadence régulière sur NVIDIA et AMD.

**État du prototype.** Sur l’image de référence, les deux callbacks TLS se terminent et le point d’entrée exécute les premiers initialiseurs. Le programme configure sa mémoire graphique et réserve deux plages virtuelles dans chacun des profils Series X et Series S. Le premier arrêt reproductible survient sur une demande `XMemVirtualAlloc` qui exige des pages engagées. Le jeu n’atteint pas sa première image. Un test graphique indépendant rend deux cibles hors écran et relit huit pixels par adaptateur. Il passe sur une GeForce RTX 5080 et sur le circuit Radeon intégré du même PC.

## Construire sous Windows

Utiliser Rust stable pour la cible MSVC x64, les outils de compilation Visual Studio avec le SDK Windows et Python x64 3.10 ou ultérieur. Depuis la racine du dépôt, dans PowerShell :

```powershell
cargo build --release --locked
python -m venv .venv
.\.venv\Scripts\python -m pip install -e './research[dev]'
git config core.hooksPath .githooks
```

## Exécuter

`inspect` lit un fichier PE et donne son empreinte, son point d’entrée, ses sections et ses imports. Avec `--json`, il décrit aussi les adresses nécessaires au démarrage. `boot` exécute les instructions dans un espace mémoire invité. Remplacer le chemin d’exemple par celui du fichier local.

```powershell
$image = 'D:\images\exemple.exe'
.\target\release\kelvaroq inspect $image
.\target\release\kelvaroq boot $image --python .\.venv\Scripts\python.exe
.\target\release\kelvaroq gpu
```

`boot` rend le code de sortie 0 si le point d’entrée revient, 2 si l’exécution invitée s’arrête avec un diagnostic, 1 pour une erreur d’outil ou de chargement. La valeur renvoyée par le programme invité figure dans le JSON. `boot --console series-s` sélectionne le profil Series S. Le choix par défaut est `series-x`. `gpu --adapter 0` limite la sonde à un adaptateur DXGI. Les deux commandes peuvent être exécutées indépendamment.

## Vérifier les shaders sur la RTX 5080

Le banc de référence compile deux révisions précises du traducteur GFX10, exécute les programmes sur l’adaptateur matériel nommé et compare les valeurs relues. Il couvre huit cas d’extension de signe et deux programmes qui sélectionnent des textures différentes selon la voie. Sur la RTX 5080 de développement, les huit résultats entiers et les 64 échantillons de texture concordent.

```powershell
python scripts/check_shaders.py --adapter 'RTX 5080'
```

Git et Cargo sont nécessaires. Le premier lancement récupère les révisions, ensuite les objets Git sont conservés sous `target/shader-reference/`. L’option `--source` accepte aussi un clone local contenant les deux commits. Ce banc valide un traducteur externe sur des programmes contrôlés. Le raccordement aux shaders émis pendant le jeu reste à faire.

## Travailler sur le projet

- Pour construire, relire et tester une modification, suivre les [règles de contribution](CONTRIBUTING.md).
- Pour les choix d’architecture, les critères de compatibilité et le protocole de mesure, lire [documentation.md](documentation.md).
- Pour les observations sur le binaire, les adresses et l’arrêt reproductible, consulter le [carnet de décompilation](décompile.md).

Le dépôt contient le code, le logo et des programmes de test générés à partir de sources originales. Le fichier étudié est fourni localement par l’opérateur. Les conditions applicables au projet figurent dans [LICENSE](LICENSE).
