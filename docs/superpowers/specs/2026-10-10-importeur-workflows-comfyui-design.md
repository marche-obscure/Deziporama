# Importeur de workflows ComfyUI — Design

Date : 2026-10-10

## Objectif

Ranger automatiquement dans ComfyUI les workflows téléchargés manuellement depuis Discord, sans accès à l'API Discord (aucun risque pour le compte utilisateur).

**Succès =** un `.zip` ou `.json` de workflow téléchargé depuis Discord apparaît, quelques secondes plus tard, dans le bon sous-dossier des workflows ComfyUI (dézippé si besoin), sans manipulation supplémentaire.

## Décisions validées

- Accès Discord : aucun. L'utilisateur télécharge lui-même ; l'applicatif surveille le dossier Téléchargements.
- Le choix du « salon » devient le choix d'un **sous-dossier de destination**.
- Destination racine par défaut : `G:\GenerateurIA\ComfyUI\User\default\workflows`
- Dossier surveillé par défaut : `C:\Users\JEM\Downloads`
- Interface : petite fenêtre (Tkinter).
- Zip d'origine envoyé à la **Corbeille** après extraction réussie.

## Technique

- Python 3.14, Tkinter (inclus).
- Dépendances : `watchdog` (surveillance), `send2trash` (Corbeille), `pytest` (tests).
- Lancement : `Lancer.bat` (double-clic).

## Composants

| Fichier | Rôle | Dépend de |
|---|---|---|
| `importer.py` | Logique pure : détection d'un workflow, import d'un `.json`, extraction sécurisée d'un `.zip`, gestion des doublons. Aucune dépendance UI. | stdlib, `send2trash` |
| `watcher.py` | Surveillance du dossier (watchdog), attente de fin de téléchargement, appel de `importer`, remontée des résultats via callback. | `watchdog`, `importer` |
| `app.py` | Fenêtre Tkinter, configuration, journal. | `watcher`, `importer` |
| `config.json` | Réglages persistés (créé au premier lancement). | — |
| `tests/test_importer.py` | Tests de `importer`. | `pytest` |

## Interface (app.py)

- Champ + bouton « Parcourir » : dossier surveillé.
- Champ + bouton « Parcourir » : dossier racine des workflows.
- Liste déroulante : sous-dossier de destination (sous-dossiers existants de la racine + entrée « (racine) »), bouton « Nouveau… » pour en créer un.
- Case à cocher : « Traiter aussi les fichiers déjà présents au démarrage » (décochée par défaut).
- Bouton Démarrer / Arrêter.
- Journal horodaté (succès en vert, ignorés en gris, erreurs en rouge).
- Les réglages sont sauvegardés dans `config.json` à chaque modification.
- Le sous-dossier choisi est lu au moment où chaque fichier est traité (changer de sous-dossier ne nécessite pas de redémarrer la surveillance).

### Ajouts du 2026-10-10 : zone de notification et lancement automatique

- Case « Lancer à l'ouverture de session Windows » : valeur `ImporteurWorkflowsComfyUI` dans `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` (sans droits administrateur), commande `pythonw.exe app.py --demarrage`. L'état de la case est lu dans le registre.
- Lancé avec `--demarrage` : la fenêtre ne s'ouvre pas, l'icône apparaît près de l'horloge et la surveillance démarre avec les derniers réglages.
- Bouton Réduire : la fenêtre quitte la barre des tâches, une icône apparaît dans la zone de notification (clic = Afficher ; clic droit = Afficher / Quitter ; infobulle = état de la surveillance).
- Bouton Fermer : boîte « Réduire près de l'horloge / Quitter / Annuler ».
- Dépendances ajoutées : `pystray`, `Pillow`.
- Une seule copie à la fois (mutex nommé `Local\ImporteurWorkflowsComfyUI`). Un deuxième lancement manuel affiche « Afficher celui déjà lancé / Annuler » puis se ferme ; « Afficher » fait réapparaître la fenêtre de la copie en cours (événement nommé). Relancé par Windows à l'ouverture de session alors qu'il tourne déjà : se ferme sans rien afficher.

## Détection

- Extensions ignorées : `.crdownload`, `.tmp`, `.part`, tout autre que `.json`/`.zip`.
- Fichier prêt = taille stable sur 2 contrôles espacés de 1 s et ouvrable en lecture (délai max 120 s, sinon erreur).
- **JSON de workflow** = objet JSON qui contient (`nodes` liste ET `links`) — format UI — OU dont toutes les valeurs sont des objets avec une clé `class_type` — format API. Sinon : ignoré (journal gris), fichier laissé en place.
- **ZIP de workflow** = archive valide contenant au moins un `.json` répondant au critère ci-dessus. Sinon : ignoré, laissé en place.

## Rangement

- Destination effective = `racine\<sous-dossier>` (créée si absente).
- `.json` : **déplacé** vers la destination.
- `.zip` : extrait intégralement dans `destination\<nom du zip sans extension>\`, puis zip envoyé à la Corbeille.
  - Exception (ajout du 2026-10-10) : si la racine du zip ne contient **qu'un seul dossier et aucun fichier**, ce dossier est placé directement dans `destination\<nom du dossier intérieur>\` (pas de double dossier). Exemple : `Ep33 Workflows.zip` → `destination\EP33 Workflows\`.
  - Le dossier technique macOS `__MACOSX` n'est ni extrait ni pris en compte dans cette règle.
  - Le nom du dossier créé par le dézippage est mis en forme : majuscule en tête de chaque mot, reste en minuscules (mots séparés par espace, `_` ou `-`). Exemple : `EP33 Workflows` → `Ep33 Workflows`. Le contenu du dossier et les `.json` importés seuls gardent leur nom.
- Doublons : jamais d'écrasement ; suffixe ` (2)`, ` (3)`… sur le fichier `.json` ou le dossier d'extraction.
- Extraction sécurisée : toute entrée dont le chemin résolu sort du dossier d'extraction (`..`, chemin absolu, lecteur) est refusée → l'archive entière est rejetée (erreur, rien d'extrait, zip laissé en place).
- Extraction atomique : extraction dans un dossier temporaire à côté de la destination, puis renommage ; en cas d'erreur, le dossier temporaire est supprimé.

## Erreurs

- Zip corrompu, destination inaccessible (G: absent), fichier verrouillé trop longtemps : message rouge dans le journal, fichier source laissé en place.
- Aucune erreur ne doit arrêter la surveillance.
- Au démarrage, si la racine des workflows n'existe pas : message d'erreur, surveillance non démarrée.

## Tests

- `tests/test_importer.py` (pytest, dossiers temporaires) :
  - détection JSON format UI, format API, JSON non-workflow, JSON invalide ;
  - zip avec workflow, zip sans workflow, zip corrompu, zip avec chemin `..` ;
  - import `.json` (déplacement), extraction `.zip` (contenu complet + zip parti à la Corbeille, Corbeille mockée) ;
  - doublons (`(2)`, `(3)`).
- Essai manuel : lancer l'application, déposer un zip de workflow dans le dossier surveillé, vérifier le résultat dans ComfyUI.

## Hors périmètre

- Toute connexion à Discord.
- Démarrage automatique avec Windows, icône système.
