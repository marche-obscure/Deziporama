# Deziporama — ComfyUI workflow importer — Design

Date: 2026-10-10 (updated as features were added the same day)

## Goal

Automatically file into ComfyUI the workflows downloaded by hand from Discord, without using the Discord API (no risk for the user's account).

**Success =** a workflow `.zip` or `.json` downloaded from Discord shows up, a few seconds later, in the right subfolder of the ComfyUI workflows (extracted if needed), with no extra step.

## Decisions

- Discord access: none. The user downloads the files; the application watches the Downloads folder.
- Choosing the Discord "channel" becomes choosing a **destination subfolder**.
- Default workflows root: `G:\GenerateurIA\ComfyUI\User\default\workflows` (the author's install; other users pick theirs with Browse…).
- Default watched folder: the user's `Downloads` folder.
- UI: a small Tkinter window, in English.
- The original zip is sent to the **Recycle Bin** after a successful extraction.

## Technology

- Python 3.14, Tkinter (bundled), Windows only.
- Dependencies: `watchdog` (watching), `send2trash` (Recycle Bin), `pystray` + `Pillow` (tray icon, logo), `pytest` (tests).
- Launch: `Start Deziporama.bat` (double-click); it creates `.venv` and installs the dependencies when needed.

## Components

| File | Role | Depends on |
|---|---|---|
| `importer.py` | Pure logic: workflow detection, `.json` import, safe `.zip` extraction, duplicates, folder name formatting. No UI. | stdlib, `send2trash` |
| `watcher.py` | Folder watching (watchdog), waiting for downloads to finish, calling `importer`, reporting results through a callback. | `watchdog`, `importer` |
| `app.py` | Tkinter window, configuration, log, dialogs, entry point. | all modules below |
| `tray.py` | Notification-area icon (Show / Quit). | `pystray`, `logo` |
| `autostart.py` | Start at Windows sign-in (user's Run registry key). | `winreg` |
| `single_instance.py` | One copy at a time (named mutex) and "show" signal (named event). | `ctypes` |
| `shortcut.py` | Desktop shortcut creation (PowerShell / WScript.Shell). | `logo` |
| `logo.py` | Icon and banner taken from `assets/deziporama.webp`; `.ico` generation. | `Pillow` |
| `config.json` | Saved settings (created on first launch, not versioned). | — |

## Window (app.py)

- Logo banner at the top; logo icon in the title bar and taskbar.
- Field + Browse… button: watched folder.
- Field + Browse… button: workflows root folder.
- Drop-down: destination subfolder (existing subfolders of the root + "(root)"), "New…" button to create one (names leaving the root or invalid for Windows are rejected).
- Checkbox "Also process files already present when starting" (off by default).
- Checkbox "Start at Windows sign-in (minimized, watching)".
- Buttons: Start / Stop, "Retry errors" (enabled only when an import failed), "Create desktop shortcut" (disabled when the shortcut exists).
- Timestamped log: imported in green, ignored in grey, warnings in orange, errors in red.
- Settings are saved to `config.json` on every change (atomic write; wrong types fall back to defaults).
- The chosen subfolder is read when each file is handled (no restart needed after changing it).
- Every dialog is centered on the screen.

## Notification area and Windows integration

- Minimize: the window leaves the taskbar and an icon appears in the notification area (click = Show; right-click = Show / Quit; tooltip = watching state).
- Close: dialog "Minimize to tray / Quit / Cancel".
- Start at sign-in: value `ImporteurWorkflowsComfyUI` in `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` (no admin rights), command `pythonw.exe app.py --at-login`. The checkbox state is read from the registry; when enabled, the entry is rewritten on each launch so it always holds the current command. The legacy flag `--demarrage` written by older versions is still recognized.
- Started with `--at-login`: no window, tray icon shown, watching starts with the last settings.
- Desktop shortcut `Deziporama.lnk` (target `pythonw.exe app.py`, icon `assets\deziporama.ico` generated from the logo):
  - offered once on the first manual launch (`desktop_shortcut_asked` in `config.json`), never at sign-in, never if it already exists;
  - the button state is checked when the window opens, when it comes back from the tray and after creation (no periodic check).
- One copy at a time (named mutex `Local\ImporteurWorkflowsComfyUI`). A second manual launch shows "Show the running one / Cancel" and exits; "Show" brings the running copy's window to the front. A second launch at sign-in exits silently.

## Detection

- Ignored extensions: `.crdownload`, `.tmp`, `.part`, anything other than `.json` / `.zip`.
- File ready = size stable over 2 checks 1 s apart and readable (120 s maximum, otherwise an error). Empty placeholder files (Firefox) are skipped silently.
- **Workflow JSON** = JSON object holding (`nodes` list AND `links`) — UI format — OR whose values are all objects with a `class_type` key — API format. Otherwise ignored (grey log line), file left in place. Limit: 50 MB.
- **Workflow ZIP** = valid archive holding at least one `.json` matching the rule above. Otherwise ignored, left in place. Encrypted zips or unsupported compression are ignored, not errors.

## Filing

- Destination = `root\<subfolder>` (created if missing).
- `.json`: copied under a temporary name, renamed, then the original is deleted (never a truncated workflow).
- `.zip`: fully extracted into `destination\<zip name without extension>\`, then the zip is sent to the Recycle Bin.
  - If the zip root holds **a single folder and no file**, that folder is placed directly as `destination\<inner folder name>\` (no nested folder). Example: `Ep33 Workflows.zip` → `destination\Ep33 Workflows\`.
  - The macOS technical folder `__MACOSX` is neither extracted nor taken into account by that rule.
  - The created folder name is formatted: capital first letter of each word, the rest lowercase (words split by space, `_` or `-`). Example: `EP33 Workflows` → `Ep33 Workflows`. The folder content and standalone `.json` files keep their names.
  - Archives larger than 2 GB once extracted are rejected.
- Duplicates: never overwrite; ` (2)`, ` (3)`… suffix on the `.json` file or the extraction folder.
- Safe extraction: any entry whose resolved path escapes the extraction folder (`..`, absolute path, drive) is rejected → the whole archive is rejected (error, nothing extracted, zip left in place).
- Atomic extraction: extraction into a temporary folder next to the destination, then rename; on error the temporary folder is deleted.

## Errors

- Corrupt zip, unreachable destination (G: missing), file locked too long: red log line, source file left in place, "Retry errors" enabled.
- Recycle Bin failure after a successful extraction: reported as imported with an orange warning.
- No error stops the watching. If the watched folder disappears, watching stops and an error is logged.
- On Start, if the workflows root does not exist: error message, watching not started.

## Tests

- `pytest` suite under `tests/` (temporary folders, test registry key, fakes for the tray and the registry in window tests).
- `tests/test_english.py` guards that the source code (strings and comments) stays in English.
- Manual check: start the application, download a workflow zip, check the result in ComfyUI.

## Out of scope

- Any connection to Discord.
