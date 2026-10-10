# Importeur de workflows ComfyUI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Petite application Windows qui surveille le dossier Téléchargements et range automatiquement les workflows ComfyUI (`.json` / `.zip`) dans un sous-dossier choisi des workflows ComfyUI, en dézippant les archives.

**Architecture:** `importer.py` contient toute la logique métier pure (détection, import, extraction sécurisée), testée unitairement. `watcher.py` relie watchdog à `importer` dans un thread de travail et remonte des `ImportResult` via callback. `app.py` est une fenêtre Tkinter qui reçoit ces résultats par une `queue.Queue` lue avec `after()`.

**Tech Stack:** Python 3.14, Tkinter, watchdog, send2trash, pytest.

**Spec:** `docs/superpowers/specs/2026-10-10-importeur-workflows-comfyui-design.md`

## Global Constraints

- Dossier surveillé par défaut : `C:\Users\JEM\Downloads` (calculé : `Path.home() / "Downloads"`).
- Racine workflows par défaut : `G:\GenerateurIA\ComfyUI\User\default\workflows`.
- Extensions traitées : `.json`, `.zip` uniquement (insensible à la casse). Ignorées : `.crdownload`, `.tmp`, `.part`, et tout le reste.
- Fichier prêt : taille stable sur 2 contrôles espacés de 1 s + ouvrable en lecture ; délai max 120 s.
- Jamais d'écrasement : suffixes ` (2)`, ` (3)`…
- Zip d'origine envoyé à la Corbeille (`send2trash`) uniquement après extraction réussie.
- Toute erreur laisse le fichier source en place et n'arrête pas la surveillance.
- `config.json` à la racine du projet, ignoré par git.
- Textes de l'interface en français.

## Review Focus

1. Chrome/Edge téléchargent en `.crdownload` puis **renomment** : l'événement est un `moved` (pas `created`) → le fichier final doit être traité. Test : Task 3 `test_rename_from_crdownload_is_processed`.
2. Un même fichier déclenche plusieurs événements (`created` + `modified`) → il doit être importé **une seule fois**. Test : Task 3 `test_file_processed_once`.
3. JSON enregistré avec BOM UTF-8 (fréquent sous Windows) → doit être reconnu comme workflow. Test : Task 1 `test_json_with_bom`.
4. JSON valide mais pas un objet (liste, nombre) ou fichier vide → ignoré sans exception. Test : Task 1 `test_non_object_json_ignored`.
5. Destination inaccessible (disque G: débranché) → `ImportResult` en erreur, source intacte, pas de crash. Test : Task 2 `test_unwritable_destination_is_error`.

---

### Task 1: Mise en place + détection des workflows

**Files:**
- Create: `requirements.txt`, `importer.py`, `tests/__init__.py` (vide), `tests/test_importer.py`

**Interfaces:**
- Produces:
  - `is_workflow_data(data: object) -> bool`
  - `is_workflow_json(path: Path) -> bool` — lit en `utf-8-sig`, `False` sur toute erreur de lecture/parse.
  - `is_workflow_zip(path: Path) -> bool` — `False` si zip invalide.

- [ ] **Step 1: `requirements.txt`**

```
watchdog>=6.0
send2trash>=1.8
pytest>=8.0
```

Run: `python -m venv .venv` puis `.venv\Scripts\pip install -r requirements.txt` — Expected: installation sans erreur.

- [ ] **Step 2: Write the failing tests** (`tests/test_importer.py`, fichiers créés dans `tmp_path`)

```python
UI = {"nodes": [], "links": [], "version": 0.4}
API = {"3": {"class_type": "KSampler", "inputs": {}}, "4": {"class_type": "SaveImage", "inputs": {}}}

def test_ui_format_detected(): assert is_workflow_data(UI)
def test_api_format_detected(): assert is_workflow_data(API)
def test_other_dict_ignored(): assert not is_workflow_data({"name": "x"})
def test_empty_dict_ignored(): assert not is_workflow_data({})
def test_non_object_json_ignored(tmp_path):  # [1,2], 42, fichier vide, texte invalide → False
def test_json_with_bom(tmp_path):  # json.dumps(UI) écrit en encoding="utf-8-sig" → True
def test_zip_with_workflow(tmp_path):  # zip contenant "sub/wf.json" (UI) + "img.png" → True
def test_zip_without_workflow(tmp_path):  # zip contenant "readme.txt" + "data.json" ({"a":1}) → False
def test_corrupt_zip(tmp_path):  # fichier .zip contenant b"pas un zip" → False
```

- [ ] **Step 3: Run** `.venv\Scripts\python -m pytest tests -v` — Expected: FAIL (ImportError).

- [ ] **Step 4: Implement in `importer.py`**

Format UI = dict avec `nodes` de type list ET clé `links`. Format API = dict non vide dont toutes les valeurs sont des dicts contenant `class_type`. `is_workflow_zip` : `zipfile.ZipFile`, parcourt les entrées `.json` (hors dossiers), lit avec `decode("utf-8-sig")`, `True` au premier workflow ; attrape `zipfile.BadZipFile`, `OSError`, `ValueError`.

- [ ] **Step 5: Run** tests — Expected: PASS.

- [ ] **Step 6: Commit** — `git add requirements.txt importer.py tests` ; message `Ajoute la détection des workflows ComfyUI`.

---

### Task 2: Import et extraction sécurisée

**Files:**
- Modify: `importer.py`
- Test: `tests/test_importer.py`

**Interfaces:**
- Consumes: Task 1.
- Produces:

```python
@dataclass
class ImportResult:
    status: str            # "imported" | "ignored" | "error"
    source: Path
    target: Path | None = None
    message: str = ""

def unique_path(path: Path) -> Path
def import_file(source: Path, dest_dir: Path, trash: Callable[[str], None] = send2trash) -> ImportResult
```

- [ ] **Step 1: Write the failing tests**

```python
def test_unique_path_free(tmp_path): assert unique_path(tmp_path / "a.json") == tmp_path / "a.json"
def test_unique_path_suffixes(tmp_path):
    # a.json et "a (2).json" existent → "a (3).json" ; dossier "pack" existe → "pack (2)"
def test_import_json_moves(tmp_path):
    # status "imported", target == dest/"wf.json", source n'existe plus, contenu identique
    # dest_dir inexistant → créé
def test_import_json_duplicate(tmp_path):  # dest/wf.json existe → target dest/"wf (2).json", ancien intact
def test_import_non_workflow_ignored(tmp_path):  # status "ignored", source toujours là
def test_import_zip_extracts_all(tmp_path):
    # zip "pack.zip" : "wf.json"(UI), "images/a.png" → dest/"pack"/wf.json et dest/"pack"/images/a.png
    # trash appelé une fois avec str(source) (trash = liste.append), status "imported", target dest/"pack"
def test_import_zip_duplicate_folder(tmp_path):  # dest/"pack" existe → dest/"pack (2)"
def test_zip_slip_rejected(tmp_path):
    # zip avec wf.json(UI) + entrée "../evil.txt" → status "error", trash non appelé,
    # aucun evil.txt hors dest, aucun dossier "pack*" ni temporaire restant dans dest, source intacte
def test_absolute_path_entry_rejected(tmp_path):  # entrée "C:/evil.txt" → "error", même vérifs
def test_corrupt_zip_ignored(tmp_path):  # status "ignored", source intacte
def test_unwritable_destination_is_error(tmp_path):
    # dest_dir = un FICHIER existant / "sous" (création impossible) → status "error", source intacte, pas d'exception
```

- [ ] **Step 2: Run** — Expected: FAIL.

- [ ] **Step 3: Implement**

`import_file` : extension `.json` → `is_workflow_json` sinon `ignored` ; `dest_dir.mkdir(parents=True, exist_ok=True)` ; `shutil.move` vers `unique_path(dest_dir / source.name)`.
Extension `.zip` → `is_workflow_zip` sinon `ignored` ; cible = `unique_path(dest_dir / source.stem)` ; extraction dans `tempfile.mkdtemp(dir=dest_dir, prefix=".import-")` ; **avant d'extraire**, pour chaque entrée vérifier que `(tmp / name).resolve()` est relatif à `tmp.resolve()` et que `PurePosixPath(name)` / `PureWindowsPath(name)` n'est ni absolu ni avec lecteur, sinon `ValueError("Chemin dangereux dans l'archive : …")` ; puis `extractall(tmp)`, `tmp.rename(cible)`, ensuite seulement `trash(str(source))`. Toute exception → `shutil.rmtree(tmp, ignore_errors=True)` et `ImportResult("error", source, None, message en français)`. Tout le corps de `import_file` est protégé : aucune exception ne sort.

- [ ] **Step 4: Run** — Expected: PASS (tous les tests de Task 1 et 2).

- [ ] **Step 5: Commit** — message `Ajoute l'import des JSON et l'extraction sécurisée des zips`.

---

### Task 3: Surveillance du dossier

**Files:**
- Create: `watcher.py`, `tests/test_watcher.py`

**Interfaces:**
- Consumes: `import_file`, `ImportResult` (Task 2).
- Produces:

```python
def is_candidate(path: Path) -> bool          # .json/.zip, insensible à la casse
def wait_until_ready(path: Path, timeout: float = 120, interval: float = 1.0) -> bool

class FolderWatcher:
    def __init__(self, watch_dir: Path, get_dest: Callable[[], Path],
                 on_result: Callable[[ImportResult], None]) -> None
    def start(self, process_existing: bool = False) -> None
    def stop(self) -> None
    @property
    def running(self) -> bool
```

- [ ] **Step 1: Write the failing tests** (`tests/test_watcher.py`) — `on_result` alimente une `queue.Queue` ; helper `wait_result(q, timeout=10)` ; `interval` réduit via un paramètre de module `READY_INTERVAL` mis à `0.1` par monkeypatch.

```python
def test_is_candidate():  # "a.JSON", "b.zip" True ; "c.crdownload", "d.tmp", "e.part", "f.png" False
def test_wait_until_ready_stable(tmp_path):  # fichier écrit → True
def test_wait_until_ready_missing(tmp_path):  # fichier inexistant, timeout=0.5 → False
def test_new_json_is_imported(tmp_path):  # start(), écrire wf.json → résultat "imported", fichier dans dest
def test_rename_from_crdownload_is_processed(tmp_path):
    # écrire "wf.json.crdownload" puis os.rename vers "wf.json" → "imported"
def test_file_processed_once(tmp_path):
    # écrire wf.json en 3 écritures successives → un seul ImportResult dans les 3 s suivantes
def test_process_existing(tmp_path):  # wf.json présent avant start(process_existing=True) → "imported"
def test_existing_not_processed_by_default(tmp_path):  # start() → rien en 2 s, fichier toujours là
def test_get_dest_read_per_file(tmp_path):  # changer la valeur renvoyée par get_dest entre deux fichiers → 2 dossiers différents
def test_stop(tmp_path):  # stop() → running False ; fichier créé ensuite non traité en 2 s
```

- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests/test_watcher.py -v` — Expected: FAIL.

- [ ] **Step 3: Implement in `watcher.py`**

Handler watchdog (`FileSystemEventHandler`) non récursif : `on_created` → `src_path`, `on_moved` → `dest_path` ; ignore dossiers et non-candidats ; met le chemin dans une `queue.Queue` de travail. Un thread de travail unique (daemon) dépile, ignore un chemin déjà en cours ou traité tant que le fichier existe (ensemble `_seen` retiré quand le fichier a disparu), appelle `wait_until_ready` (échec → `ImportResult("error", …, "Téléchargement non terminé après 120 s")`), puis `import_file(path, get_dest())`, puis `on_result`. Toute exception dans le thread est convertie en `ImportResult("error")` ; le thread ne meurt jamais. `start(process_existing=True)` enfile d'abord les candidats déjà présents. `stop()` arrête l'observer et le thread (sentinelle `None`).

- [ ] **Step 4: Run** tous les tests — Expected: PASS.

- [ ] **Step 5: Commit** — message `Ajoute la surveillance du dossier Téléchargements`.

---

### Task 4: Fenêtre, configuration, lanceur

**Files:**
- Create: `app.py`, `Lancer.bat`, `tests/test_config.py`

**Interfaces:**
- Consumes: `FolderWatcher` (Task 3), `ImportResult` (Task 2).
- Produces:

```python
CONFIG_PATH = Path(__file__).with_name("config.json")
DEFAULTS = {"watch_dir": str(Path.home() / "Downloads"),
            "workflows_root": r"G:\GenerateurIA\ComfyUI\User\default\workflows",
            "subfolder": "", "process_existing": False}
def load_config(path: Path = CONFIG_PATH) -> dict   # fusionne DEFAULTS ; fichier absent/corrompu → DEFAULTS
def save_config(cfg: dict, path: Path = CONFIG_PATH) -> None
```

- [ ] **Step 1: Write the failing tests** (`tests/test_config.py`)

```python
def test_missing_config_gives_defaults(tmp_path): assert load_config(tmp_path / "c.json") == DEFAULTS
def test_corrupt_config_gives_defaults(tmp_path):  # contenu "{oops" → DEFAULTS
def test_roundtrip(tmp_path):  # save puis load → identique ; clé manquante complétée par DEFAULTS
```

- [ ] **Step 2: Run** — FAIL ; implémenter `load_config`/`save_config` (JSON UTF-8, indent 2) ; Run — PASS.

- [ ] **Step 3: Implement the window in `app.py`** (`main()` sous `if __name__ == "__main__":`)

Widgets, dans l'ordre : « Dossier surveillé » (Entry + « Parcourir… ») ; « Dossier des workflows » (Entry + « Parcourir… ») ; « Sous-dossier » (Combobox `readonly` : « (racine) » + sous-dossiers de la racine triés, sans ceux commençant par `.`, + bouton « Nouveau… » via `simpledialog.askstring` qui crée le dossier et le sélectionne) ; Checkbutton « Traiter aussi les fichiers déjà présents au démarrage » ; bouton « Démarrer » / « Arrêter » ; `Text` en lecture seule pour le journal avec tags `ok` (vert), `ignored` (gris), `error` (rouge), lignes `HH:MM:SS  message`.
Comportement : chaque modification → `save_config`. `get_dest` lit la Combobox (« (racine) » → racine). Démarrer : si racine ou dossier surveillé inexistants → ligne rouge, pas de démarrage. Les champs dossiers sont désactivés pendant la surveillance. `on_result` fait `queue.put` ; `root.after(200, …)` vide la queue et écrit le journal : imported → `Importé : <nom> → <cible>` ; ignored → `Ignoré (pas un workflow) : <nom>` ; error → `Erreur : <nom> — <message>`. Fermeture de la fenêtre → `watcher.stop()`.

- [ ] **Step 4: `Lancer.bat`**

```bat
@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (
  python -m venv .venv || goto :err
  .venv\Scripts\pip install -r requirements.txt || goto :err
)
start "" .venv\Scripts\pythonw.exe app.py
exit /b 0
:err
echo Echec de l'installation. & pause
```

- [ ] **Step 5: Verify** — tous les tests : `.venv\Scripts\python -m pytest tests -v` → PASS. Puis essai manuel : lancer `Lancer.bat`, choisir un sous-dossier de test (« Nouveau… » → `_Test`), Démarrer, copier dans Téléchargements un zip de workflow → ligne verte, dossier extrait dans `workflows\_Test\<nom>`, zip dans la Corbeille ; copier un `.json` non-workflow → ligne grise, fichier laissé en place. Supprimer `_Test` ensuite.

- [ ] **Step 6: Commit** — `git add app.py Lancer.bat tests/test_config.py` ; message `Ajoute la fenêtre, la configuration et le lanceur`.
