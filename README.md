<img src="assets/logo.png" alt="Emblème de Kelvaroq" width="112">

# Kelvaroq

Projet privé de compatibilité Xbox Series X|S pour Windows x64, écrit en Rust avec un moteur CPU de référence pour la recherche. L’objectif est une scène jouable en **3840 × 2160 à 30 images rendues par seconde**, avec ses textures correctes et une cadence régulière sur NVIDIA et AMD.

**État du prototype.** Sur les deux profils, l’image de référence termine ses deux callbacks TLS, lit la topologie console, crée quatre événements et entre dans 36 initialiseurs. L’arrêt actuel survient dans une boucle vectorielle x64 avant la première image du jeu. Une sonde Direct3D 12 indépendante a vérifié huit pixels sur la GeForce RTX 5080 puis sur le circuit Radeon intégré du même PC.

## Lancer le paquet Windows

1. Extraire entièrement le ZIP Windows x64 dans un dossier.
2. Ouvrir **Kelvaroq.exe**. Choisir le dossier du jeu ou son exécutable. Le glisser-déposer de l’un ou l’autre sur Kelvaroq.exe fonctionne aussi.
3. Suivre le démarrage dans la fenêtre **Journal**. La fenêtre de rendu reste noire jusqu’à ce qu’une image invitée soit disponible. À l’arrêt, le diagnostic reste consultable. Fermer la fenêtre de rendu termine la session.

Le paquet inclut le moteur de référence et son interpréteur. Le dossier peut être déplacé en conservant ses fichiers ensemble. Pour traiter un dossier, le lanceur utilise l’exécutable Series déclaré dans `MicrosoftGame.config`. En l’absence de manifeste, il accepte le seul `.exe` du dossier. En cas de choix ambigu, sélectionner le fichier directement.

La fenêtre demande deux tampons Direct3D 12 de 3840 × 2160. Le journal affiche leurs dimensions après vérification sur le GPU. La fenêtre conserve le format 16:9 lors du redimensionnement. La résolution à laquelle le jeu calcule ses images sera mesurée lorsque son rendu sera raccordé.

## Construire sous Windows

Utiliser Rust stable pour la cible MSVC x64, les outils de compilation Visual Studio avec le SDK Windows et Python x64 3.10 ou ultérieur. Depuis la racine du dépôt, dans PowerShell :

```powershell
cargo build --release --locked
python -m venv .venv
.\.venv\Scripts\python -m pip install -e './research[dev]'
git config core.hooksPath .githooks
```

Pour reconstruire le ZIP privé du prototype depuis Windows, utiliser Python 3.11 ou ultérieur et exécuter `python scripts/package_windows.py`. Le script fournit les notices des composants tiers, vérifie leurs empreintes et teste l’archive décompressée hors du dépôt. Le résultat se trouve dans `target/dist/`. Le moteur de référence utilise Unicorn sous GPLv2. La notice et les sources amont correspondantes sont incluses. [Licence du moteur Unicorn](https://github.com/unicorn-engine/unicorn/blob/2.1.4/COPYING)

## Exécuter

`inspect` lit un fichier PE et donne son empreinte, son point d’entrée, ses sections et ses imports. Avec `--json`, il décrit aussi les adresses nécessaires au démarrage. `boot` exécute les instructions dans un espace mémoire invité. Remplacer le chemin d’exemple par celui du fichier local.

```powershell
$image = 'D:\images\exemple.exe'
.\target\release\kelvaroq inspect $image
.\target\release\kelvaroq boot $image --python .\.venv\Scripts\python.exe
.\target\release\kelvaroq play $image --python .\.venv\Scripts\python.exe
.\target\release\kelvaroq gpu
```

`boot` fournit un rapport JSON et rend le code de sortie 0 si le point d’entrée revient, 2 si l’exécution invitée s’arrête avec un diagnostic, 1 pour une erreur d’outil ou de chargement. `play` ouvre les fenêtres de rendu et de journal sur le même moteur. Les deux commandes acceptent `--console series-s` et utilisent le profil Series X par défaut. Le manifeste choisit le SMT. Pour comparer les résultats de découverte CPU, `--host-topology` expose les enregistrements Windows du PC et `--processor-info <capture.bin>` rejoue des enregistrements x64 bruts. Conserver `kelvaroq_simd.dll` à côté du CLI. La sonde graphique indépendante accepte `gpu --adapter 0`.

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
