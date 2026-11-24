# Carnet de décompilation

## Échantillon et méthode

Image PE32+ AMD64, version observée 1.0.2.1, SHA-256 `e95020b2fa4a721db3df59fdecf75621730ac559d8835252f6c3b658d5a08993`. Le chargeur recense 10 sections, 587 imports et deux callbacks TLS. Les adresses de cette page sont des RVA relatives à l’image. L’analyse porte sur le démarrage, les ressources graphiques et la présentation. La couverture de l’exécutable reste partielle.

Trois preuves ont des portées différentes. Le désassemblage établit la forme d’un appel et ses arguments visibles. Une exécution de fonction avec des entrées construites établit son comportement pour ces entrées. Le démarrage depuis le fichier d’origine établit quelles fonctions sont réellement atteintes avec les services actuellement disponibles. Les adresses graphiques ci-dessous proviennent des deux premières méthodes.

## Démarrage effectivement exécuté

| Ordre | RVA | Observation |
| --- | --- | --- |
| 1 et 2 | `0x55dd4f4`, `0x55e2ebc` | Les deux callbacks TLS reviennent après attachement du processus. |
| 3 | `0x56a1ec8` | Le point d’entrée commence. Le code invité initialise son cookie et demande les identifiants de processus et de thread ainsi que des horloges. |
| 4 | `0x55dd354` | Un initialiseur C résout des services de synchronisation via les modules virtuels. La table C contient quatre cases dont trois non nulles. La table C++ contient 1 115 cases dont 1 114 non nulles. Ces effectifs décrivent la table du fichier. |
| 5 | `0x5c1b680` | Quatrième initialiseur entré sur ce parcours. L’appel à `memset` dont l’adresse de retour est `0x14714b4` se termine dans la référence actuelle. |
| 6 | `0x4e72fdf` | Écriture non alignée de 32 octets de YMM0 vers l’adresse RCX. Elle reproduisait une instruction invalide dans Unicorn 2.1.4. Une fixture indépendante vérifie l’écriture sur une adresse impaire, les voies hautes et les permissions. Le démarrage franchit désormais cette instruction. |
| 7 | `0x55debac` | Appel de `advapi32.dll!RegOpenKeyW`. Adresse de retour `0x55debb2`. L’ouverture, la lecture et la fermeture aboutissent dans les deux profils. |
| 8 | `0x1e1ceec` | Copie vectorielle non alignée avec `VMOVDQU`. Le contenu complet des deux voies est conservé par la référence. |
| 9 | `0x1e1cfe0` | Appel de `d3d12_xs.dll!D3D12ConfigureVirtualMemoryX`. Premier arrêt reproduit pour les deux modèles, adresse de retour `0x1e1cfe5`. |

La fonction à `0x55deb88` prépare le handle prédéfini `HKEY_LOCAL_MACHINE`, un sous-chemin UTF-16 et une sortie sur la pile. Elle teste le code de retour de l’ouverture. En cas de succès, elle cherche la valeur `ConsoleMode` dans `Software\Microsoft\Windows NT\CurrentVersion\OEM`, puis ferme la clé. La suite compare la donnée lue à plusieurs constantes. Les valeurs de modèle proposées par le dépôt étudié, `0x64` et `0x60`, produisent respectivement les types 7 et 6 en exécutant cette fonction avec le registre virtuel. Cette expérience confirme la branche du binaire. La valeur n’a pas été lue sur une console physique.

### Configuration de la mémoire graphique

Au retour prévu `0x1e1cfe5`, le code teste le HRESULT. L’appel suivant observé statiquement est `XMemVirtualAlloc` à `0x1e1d00a`. La valeur déjà préparée dans RSI donne la taille prévue de la réservation virtuelle. Le test n’a engagé aucune de ces quantités en mémoire physique.

| Profil | Résultat de la détection | DWORD à l’offset 4 de la structure de 32 octets | Taille prévue pour la réservation suivante |
| --- | --- | --- | --- |
| Series X | 7 | 4 | 24 Gio |
| Series S | 6 | 3 | 16 Gio |

Les sept autres DWORD valent zéro dans les deux exécutions. Cette mesure a révélé un défaut du moteur de référence initial. Unicorn 2.1.4 acceptait un `VXORPS xmm0,xmm0,xmm0` tout en conservant les 128 bits hauts de YMM0. Une instruction de stockage ultérieure plaçait donc des octets anciens dans la structure. Un test de régression démarre le registre entièrement à un et vérifie les 256 bits après l’instruction. La suite couvre aussi les déplacements vectoriels non alignés et `VZEROUPPER`.

Pour reproduire, exécuter `inspect`, comparer l’empreinte ci-dessus, puis `boot` comme indiqué dans le README. Le JSON contient deux entrées dans `completed`, `stage = entry`, `initializers_entered = 4` et `stop.return_rva = 0x1e1cfe5`. Le code de sortie attendu est 2. La suite synthétique peut être rejouée sans posséder l’échantillon.

## Textures, barrières et dessin

| RVA | Observation | Conséquence à tester dans le backend |
| --- | --- | --- |
| `0x979c75`, `0x979c9f` | Création d’un calculateur de texture, puis appel virtuel à l’offset `+0x10` pour son layout. | Vérifier le placement par sous-ressource avec une texture à motifs distincts par mip, couche et plan. Contrôler les données après transfert. |
| `0x95e0`, `0x3210d` | Construction de groupes de barrières de type 2, en-tête de 16 octets et entrées de 40 octets portant une ressource. Le chemin de soumission rejoint le slot `+0x490`. | Des entrées synthétiques de zéro, un et deux groupes ont servi à contrôler le comptage. Conserver la granularité de chaque ressource et tester la visibilité des écritures. |
| `0x24800d5`, `0x247fe66` | Un chemin tente le pipeline en cache via `+0x218`. Un résultat nul permet un repli via `+0x1f0`. | Tester le cache froid et chaud avec le même résultat de dessin. Une entrée de cache manquante peut mener à un pipeline valide. |
| `0x4e33f91`, `0x555e976` | Deux sites d’`ExecuteIndirect` passent une commande maximale, une ressource d’arguments et un décalage, sans tampon de comptage sur ces sites. | Tester le contenu et le décalage effectifs du tampon avant toute optimisation de regroupement. Ces deux sites ne décrivent pas tous les dessins. |

## Présentation et reconstruction temporelle

- La fonction à `0x28f03db` prépare une structure temporelle. Le chemin observé utilise l’identifiant `0x10001`, inverse le signe du jitter, fournit des facteurs unitaires dans ce cas et écrit un indicateur de réinitialisation à `+0x198`. Il reste à vérifier quels tampons et quelles unités arrivent réellement à chaque image.
- Les fonctions à `0x24821dd` et `0x24824c1` utilisent un identifiant de trame issu du même global à `0x75e0e88` pour la soumission et la présentation. Des appels synthétiques à un et deux plans donnent un pas de `0x48` octets entre descripteurs de plans. Un identifiant commun permettrait de relier les traces CPU et GPU lorsque le chemin sera raccordé.

La référence actuelle s’arrête dans l’initialisation du processus. Les observations statiques n’établissent encore ni la cause des textures manquantes d’une scène particulière ni un débit d’images du jeu sur PC.
