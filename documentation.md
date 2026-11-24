# Architecture et décisions

## Chemin vers une première image

Le chargeur Rust produit un plan d’image contrôlé. Le worker de référence relit le fichier, vérifie son SHA-256 et le cartographie à sa base préférée dans Unicorn. Les instructions x64 accèdent aux pages invitées. La table des imports dirige les appels vers les services émulés. Les fonctions TLS précèdent le point d’entrée. Les deux commandes `boot` et `gpu` ont aujourd’hui des chemins distincts. Il reste à relier les commandes graphiques invitées au backend.

| Décision | Motif | Critère de passage |
| --- | --- | --- |
| Référence CPU à un thread, horloge virtuelle et refus explicite d’un service inconnu | Rejouer le démarrage et comparer les effets mémoire d’un changement. | Même fichier, mêmes callbacks, même premier arrêt et mêmes données de test. |
| Rust et Direct3D 12 pour l’hôte Windows | Utiliser la même API hôte sur les pilotes NVIDIA et AMD. | Relecture identique des cibles sur chaque adaptateur. |
| Chemin x64 rapide envisagé après la référence | Un interpréteur instrumenté sert à diagnostiquer le démarrage. Le débit de production reste à mesurer. | Rejouer la suite ABI, exceptions, TLS et synchronisation sur les deux moteurs avant de retenir une implémentation. |
| Traduction GPU organisée autour des ressources et files | Une zone mémoire peut changer de propriétaire ou héberger des vues différentes. | Tests d’alias, de première copie et d’attente inter-files avec contenu attendu. |
| Upscaling et génération d’images après la présentation native | Les algorithmes temporels ont besoin de profondeur, mouvement, jitter, exposition et identifiant d’image cohérents. | Vérifier les discontinuités de caméra et isoler le HUD. Compter séparément les images rendues et générées. |

## Enseignements du dépôt examiné

Le corpus local rassemble **153 PR**, du premier numéro présent au n° 216. L’instantané du code étudié est `2119b0e44c53aa9648307b0c5c73590290305b1f`. Le nombre de PR ne renseigne ni sur la qualité de l’équipe ni sur la cause d’une trame lente. Trois cas expliquent des choix précis de Kelvaroq.

- Déplacer une copie sur une autre file peut déplacer l’attente sur son consommateur. Pour chaque transfert coûteux, mesurer l’enregistrement CPU, la soumission, la durée GPU et l’attente d’une fence. Avant d’accuser le débit mémoire, relier ces quatre temps à une même ressource et une même trame. [PR 71](https://github.com/fxceless/victory-fork/pull/71)
- Deux vues d’une même plage peuvent référencer les mêmes octets pendant qu’une écriture reste en vol. Le futur suivi de ressources devra associer plage, génération, dernier écrivain et point de synchronisation. Le test devra lire la version attendue après réutilisation de cette plage. [PR 191](https://github.com/fxceless/victory-fork/pull/191)
- Un premier transfert doit aussi initialiser une page dont le contenu attendu vaut zéro. Le test remplira d’abord la destination d’une valeur distinctive, puis vérifiera le premier transfert, une mise à jour partielle et une réutilisation. [PR 206](https://github.com/fxceless/victory-fork/pull/206)

Dans le chemin de barrières examiné, une barrière UAV globale perd l’identité des ressources décrites dans certains appels invités. La relecture du binaire a identifié un producteur de groupes de barrières qui fournit justement ces ressources. Il faut conserver cette information jusqu’au backend pour pouvoir tester portée et dépendances. Le lien avec une texture précise manquante reste à démontrer par une capture reproductible. [Code examiné](https://github.com/fxceless/victory-fork/blob/2119b0e44c53aa9648307b0c5c73590290305b1f/crates/victory-gpu/src/list.rs#L1934)

### Réutilisation validée sur le démarrage

Le dépôt de référence associe `ConsoleMode` aux deux modèles. Kelvaroq réimplémente un registre en mémoire et applique ces deux valeurs. Appelée isolément, la même fonction du binaire renvoie 7 dans le profil X et 6 dans le profil S. Depuis le point d’entrée normal, les deux sélections produisent ensuite des tailles de mémoire différentes. C’est un comportement que l’on peut reprendre et tester indépendamment. [Profil de plateforme examiné](https://github.com/fxceless/victory-fork/blob/2119b0e44c53aa9648307b0c5c73590290305b1f/crates/victory-hle/src/modules/xsystem.rs#L162)

Le backend étudié annonce à l’invité la plage d’adresses de l’application hôte lors de la configuration graphique. Kelvaroq exécute aujourd’hui le CPU dans un espace virtuel distinct. Reprendre ces bornes telles quelles ferait une promesse que son allocateur ne peut pas tenir. Kelvaroq publie désormais une plage virtuelle invitée et y réserve les deux premiers pools observés. Ces réservations tiennent compte de l’image, de la pile et des autres plages. Les allocations avec engagement ont désormais une mémoire CPU invitée initialisée à zéro et soumise aux permissions de page. Les attributs GPU restent associés à chaque plage pour la future liaison aux ressources. Le backend de référence distingue les deux tailles de page console comme dans le [service mémoire examiné](https://github.com/fxceless/victory-fork/blob/2119b0e44c53aa9648307b0c5c73590290305b1f/crates/victory-hle/src/modules/xmem.rs#L87). [Configuration mémoire examinée](https://github.com/fxceless/victory-fork/blob/2119b0e44c53aa9648307b0c5c73590290305b1f/crates/victory-gpu/src/device.rs#L197)

### Shaders GFX10 exécutés sur la RTX 5080

Le banc utilise directement le traducteur, la génération de DXIL, la création du pipeline Direct3D 12 et la relecture du tampon du dépôt de référence. La PR 212 seule a échoué **avant création du pipeline**, sur l’instruction scalaire `s_sext_i32_i16`. La PR 182 ajoute la traduction de cette instruction. En combinant leurs arbres de source sur la même base, l’exemple `0xface8000` renvoie bien `0xffff8000` sur la carte. Le banc épingle les deux commits et vérifie que l’arbre combiné a l’identifiant `d12d72e6a39c0313f4292b10f430ca2aac634cd8`. [PR 212](https://github.com/fxceless/victory-fork/pull/212) · [PR 182](https://github.com/fxceless/victory-fork/pull/182)

| Cas exécuté | Vérification locale sur RTX 5080 |
| --- | --- |
| Extension de signe sur 8 et 16 bits | Pour chaque largeur, comparer zéro, le plus grand positif, le plus petit négatif et moins un avec un calcul indépendant sur le CPU. Huit comparaisons réussies. |
| Sélection de texture après une branche | Parmi 32 voies, les 16 premières lisent la texture de valeur 1, les autres la texture de valeur 2. Les 32 valeurs relues correspondent. |
| Descripteur chargé ou choisi à l’intérieur d’une branche | Les 16 premières voies alternent entre les textures. Les huit suivantes choisissent la première, les huit dernières la seconde. Les 32 valeurs relues correspondent. |

L’adaptateur est sélectionné par nom. Une réussite exclusivement sur un adaptateur logiciel ne valide pas le test. Pour les futurs shaders du jeu, relever le hash du programme, les descripteurs et le mode de vague au point de soumission. Comparer ensuite les résultats du traducteur sur les mêmes entrées. Les mips, les formats compressés, les écritures partielles et les différences wave32/wave64 nécessitent leurs propres cas. [PR sur les modes de vague du cache](https://github.com/fxceless/victory-fork/pull/199) · [PR sur les écritures de canaux](https://github.com/fxceless/victory-fork/pull/146)

## Jalons mesurables

| Ordre | Livrable | Preuve requise |
| --- | --- | --- |
| 1 | Terminer les initialiseurs nécessaires à l’image de référence. | Trace jusqu’à une étape identifiable après le CRT. Relier les réservations aux pages engagées, puis aux ressources GPU en préservant leurs permissions et les alias. |
| 2 | Faire parvenir une commande graphique invitée à Direct3D 12. | Trace de l’appel invité, correspondance des ressources et pixels attendus après relecture. |
| 3 | Présenter une première image complète. | Texte, géométrie et textures attendus, image de référence, absence de ressources périmées lors du chargement. |
| 4 | Valider une séquence interactive sur deux familles GPU. | Même parcours scripté et même résolution. Répéter un démarrage à froid et un à chaud, vérifier les images, la durée des trames et les blocages. |
| 5 | Évaluer DLSS, une voie disponible sur AMD et la génération d’images. | Points d’entrée optionnels sur le pipeline de présentation, comparaison du rendu natif et des modes temporels, vérification de la latence. |

### Mesure de la cadence

30 images par seconde correspondent à **33,33 ms par image**. Pour chaque configuration, fixer la résolution, les options, le pilote et le parcours. Consigner au moins les temps médians, p95, p99, la proportion de trames au-delà du budget, le pire arrêt et le nombre d’images présentées. Mesurer aussi le fil CPU critique, la compilation des pipelines, les attentes inter-files et la charge GPU. Pour un passage jugé stable, publier la durée du passage et tous les dépassements. La première sonde hors écran fait une attente volontaire et une relecture à chaque image. Elle sert uniquement au contrôle du contenu.

## Matériel effectivement testé

Windows x64, Ryzen 9 9950X3D, 64 Go de RAM. Les deux adaptateurs de ce PC ont passé séparément le test hôte Direct3D 12. Chaque cible 2 × 2 est effacée, passe de l’état rendu à l’état source de copie, est copiée en mémoire de relecture puis vérifiée après sa fence.

| Adaptateur DXGI | Identifiants PCI | Résultat de la sonde |
| --- | --- | --- |
| NVIDIA GeForce RTX 5080 | `10de:2c02` | 4 pixels rouges puis 4 verts, canaux RGBA vérifiés. |
| AMD Radeon(TM) Graphics, intégrée | `1002:13c0` | Même contenu, huit pixels vérifiés. |

Une carte AMD dédiée, une RTX 5070, le débit du jeu, les textures du jeu et sa stabilité en charge restent à qualifier sur du matériel identifié.
