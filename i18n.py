"""User interface texts in English, French and German, and the current language."""

import ctypes

LANGUAGES = {"en": "English", "fr": "Français", "de": "Deutsch"}
DEFAULT_LANGUAGE = "en"

# Shown before any language is chosen, so it is written in the three languages.
LANGUAGE_PROMPT = ("Choose your language\n"
                   "Choisissez votre langue\n"
                   "Wählen Sie Ihre Sprache")

TEXTS = {
    "en": {
        # Window
        "watched_folder": "Watched folder:",
        "workflows_folder": "Workflows folder:",
        "subfolder": "Subfolder:",
        "new": "New…",
        "browse": "Browse…",
        "root_label": "(root)",
        "process_existing": "Also process files already present when starting",
        "autostart": "Start at Windows sign-in (minimized, watching)",
        "start": "Start",
        "stop": "Stop",
        "retry": "Retry errors",
        "create_shortcut": "Create desktop shortcut",
        "tooltip_active": "{title} — watching: active",
        "tooltip_stopped": "{title} — watching: stopped",
        # Dialogs
        "already_running": "{title} is already running\n"
                           "(its icon is in the notification area, next to the clock).\n\n"
                           "Do you want to show its window?",
        "show_running": "Show the running one",
        "cancel": "Cancel",
        "close_title": "Close",
        "close_message": "Do you want to minimize {title} to the notification area\n"
                         "(watching continues) or quit it?",
        "minimize_to_tray": "Minimize to tray",
        "quit": "Quit",
        "offer_shortcut": "Create a {title} shortcut on the desktop?",
        "yes_create": "Yes, create it",
        "no_thanks": "No thanks",
        "new_subfolder_title": "New subfolder",
        "new_subfolder_prompt": "Subfolder name:",
        "invalid_name_title": "Invalid name",
        "invalid_name_message": "The name must not start with a dot or contain \\ / : * ? \" < > |",
        "error_title": "Error",
        "cannot_create_folder": "Cannot create the folder:\n{error}",
        # Tray menu
        "tray_show": "Show",
        "tray_quit": "Quit",
        # Log
        "log_stopped": "Watching stopped.",
        "log_watching": "Watching {path}.",
        "log_watch_missing": "Error: the watched folder does not exist - {path}",
        "log_root_missing": "Error: the workflows folder does not exist - {path}",
        "log_cannot_watch": "Error: cannot watch {path} - {error}",
        "log_retrying": "Retrying {count} file(s)…",
        "log_interrupted": "Error: watching interrupted, the folder {path} cannot be found. "
                           "Check it, then click Start.",
        "log_shortcut_failed": "Error: shortcut not created - {error}",
        "log_shortcut_created": "Shortcut created on the desktop: {path}",
        "log_imported": "Imported: {name} → {target}",
        "log_warning": "Warning: {message}",
        "log_ignored": "Ignored (not a workflow): {name}",
        "log_error": "Error: {name} - {message} (fix it, then click \"Retry errors\")",
        "log_settings_not_saved": "Error: settings not saved - {error}",
        "log_autostart_failed": "Error: start at sign-in not changed - {error}",
        # Import messages
        "msg_not_workflow": "not a ComfyUI workflow",
        "msg_no_workflow_in_zip": "no ComfyUI workflow in the archive",
        "msg_unsupported": "unsupported extension",
        "msg_dangerous_path": "dangerous path in archive: {name}",
        "msg_too_large": "archive too large once extracted ({size:.1f} GB)",
        "msg_original_not_deleted": "the original file could not be deleted: {error}",
        "msg_not_trashed": "the zip could not be moved to the Recycle Bin: {error}",
        "msg_download_unfinished": "download not finished after {seconds:.0f} s",
        "msg_desktop_missing": "desktop folder not found: {path}",
        "msg_shortcut_failed": "could not create the shortcut",
    },
    "fr": {
        "watched_folder": "Dossier surveillé :",
        "workflows_folder": "Dossier des workflows :",
        "subfolder": "Sous-dossier :",
        "new": "Nouveau…",
        "browse": "Parcourir…",
        "root_label": "(racine)",
        "process_existing": "Traiter aussi les fichiers déjà présents au démarrage",
        "autostart": "Lancer à l'ouverture de session Windows (réduit, surveillance démarrée)",
        "start": "Démarrer",
        "stop": "Arrêter",
        "retry": "Réessayer les erreurs",
        "create_shortcut": "Créer le raccourci bureau",
        "tooltip_active": "{title} — surveillance active",
        "tooltip_stopped": "{title} — surveillance arrêtée",
        "already_running": "{title} est déjà lancé\n"
                           "(son icône se trouve près de l'horloge).\n\n"
                           "Voulez-vous afficher sa fenêtre ?",
        "show_running": "Afficher celui déjà lancé",
        "cancel": "Annuler",
        "close_title": "Fermer",
        "close_message": "Voulez-vous réduire {title} près de l'horloge\n"
                         "(la surveillance continue) ou le quitter ?",
        "minimize_to_tray": "Réduire près de l'horloge",
        "quit": "Quitter",
        "offer_shortcut": "Créer un raccourci {title} sur le bureau ?",
        "yes_create": "Oui, créer",
        "no_thanks": "Non merci",
        "new_subfolder_title": "Nouveau sous-dossier",
        "new_subfolder_prompt": "Nom du sous-dossier :",
        "invalid_name_title": "Nom invalide",
        "invalid_name_message": "Le nom ne doit pas commencer par un point ni contenir \\ / : * ? \" < > |",
        "error_title": "Erreur",
        "cannot_create_folder": "Impossible de créer le dossier :\n{error}",
        "tray_show": "Afficher",
        "tray_quit": "Quitter",
        "log_stopped": "Surveillance arrêtée.",
        "log_watching": "Surveillance de {path}.",
        "log_watch_missing": "Erreur : le dossier surveillé n'existe pas — {path}",
        "log_root_missing": "Erreur : le dossier des workflows n'existe pas — {path}",
        "log_cannot_watch": "Erreur : impossible de surveiller {path} — {error}",
        "log_retrying": "Nouvelle tentative pour {count} fichier(s)…",
        "log_interrupted": "Erreur : surveillance interrompue, le dossier {path} est introuvable. "
                           "Vérifiez-le puis cliquez sur Démarrer.",
        "log_shortcut_failed": "Erreur : raccourci non créé — {error}",
        "log_shortcut_created": "Raccourci créé sur le bureau : {path}",
        "log_imported": "Importé : {name} → {target}",
        "log_warning": "Attention : {message}",
        "log_ignored": "Ignoré (pas un workflow) : {name}",
        "log_error": "Erreur : {name} — {message} (corrigez puis cliquez sur « Réessayer les erreurs »)",
        "log_settings_not_saved": "Erreur : réglages non sauvegardés — {error}",
        "log_autostart_failed": "Erreur : lancement à l'ouverture de session non modifié — {error}",
        "msg_not_workflow": "pas un workflow ComfyUI",
        "msg_no_workflow_in_zip": "aucun workflow ComfyUI dans l'archive",
        "msg_unsupported": "extension non prise en charge",
        "msg_dangerous_path": "chemin dangereux dans l'archive : {name}",
        "msg_too_large": "archive trop volumineuse une fois extraite ({size:.1f} Go)",
        "msg_original_not_deleted": "le fichier d'origine n'a pas pu être supprimé : {error}",
        "msg_not_trashed": "le zip n'a pas pu être mis à la Corbeille : {error}",
        "msg_download_unfinished": "téléchargement non terminé après {seconds:.0f} s",
        "msg_desktop_missing": "dossier du bureau introuvable : {path}",
        "msg_shortcut_failed": "création du raccourci impossible",
    },
    "de": {
        "watched_folder": "Überwachter Ordner:",
        "workflows_folder": "Workflow-Ordner:",
        "subfolder": "Unterordner:",
        "new": "Neu…",
        "browse": "Durchsuchen…",
        "root_label": "(Stammordner)",
        "process_existing": "Beim Start auch bereits vorhandene Dateien verarbeiten",
        "autostart": "Bei der Windows-Anmeldung starten (minimiert, Überwachung aktiv)",
        "start": "Starten",
        "stop": "Anhalten",
        "retry": "Fehler erneut versuchen",
        "create_shortcut": "Desktop-Verknüpfung erstellen",
        "tooltip_active": "{title} — Überwachung aktiv",
        "tooltip_stopped": "{title} — Überwachung angehalten",
        "already_running": "{title} läuft bereits\n"
                           "(sein Symbol befindet sich im Infobereich neben der Uhr).\n\n"
                           "Möchten Sie das Fenster anzeigen?",
        "show_running": "Laufendes Fenster anzeigen",
        "cancel": "Abbrechen",
        "close_title": "Schließen",
        "close_message": "Möchten Sie {title} in den Infobereich minimieren\n"
                         "(die Überwachung läuft weiter) oder beenden?",
        "minimize_to_tray": "In den Infobereich minimieren",
        "quit": "Beenden",
        "offer_shortcut": "Eine {title}-Verknüpfung auf dem Desktop erstellen?",
        "yes_create": "Ja, erstellen",
        "no_thanks": "Nein, danke",
        "new_subfolder_title": "Neuer Unterordner",
        "new_subfolder_prompt": "Name des Unterordners:",
        "invalid_name_title": "Ungültiger Name",
        "invalid_name_message": "Der Name darf nicht mit einem Punkt beginnen und keines dieser Zeichen "
                                "enthalten: \\ / : * ? \" < > |",
        "error_title": "Fehler",
        "cannot_create_folder": "Der Ordner kann nicht erstellt werden:\n{error}",
        "tray_show": "Anzeigen",
        "tray_quit": "Beenden",
        "log_stopped": "Überwachung angehalten.",
        "log_watching": "Überwachung von {path}.",
        "log_watch_missing": "Fehler: Der überwachte Ordner existiert nicht – {path}",
        "log_root_missing": "Fehler: Der Workflow-Ordner existiert nicht – {path}",
        "log_cannot_watch": "Fehler: {path} kann nicht überwacht werden – {error}",
        "log_retrying": "Neuer Versuch für {count} Datei(en)…",
        "log_interrupted": "Fehler: Überwachung unterbrochen, der Ordner {path} wurde nicht gefunden. "
                           "Bitte prüfen und dann auf Starten klicken.",
        "log_shortcut_failed": "Fehler: Verknüpfung nicht erstellt – {error}",
        "log_shortcut_created": "Verknüpfung auf dem Desktop erstellt: {path}",
        "log_imported": "Importiert: {name} → {target}",
        "log_warning": "Achtung: {message}",
        "log_ignored": "Ignoriert (kein Workflow): {name}",
        "log_error": "Fehler: {name} – {message} (beheben und dann auf „Fehler erneut versuchen“ klicken)",
        "log_settings_not_saved": "Fehler: Einstellungen nicht gespeichert – {error}",
        "log_autostart_failed": "Fehler: Start bei der Anmeldung nicht geändert – {error}",
        "msg_not_workflow": "kein ComfyUI-Workflow",
        "msg_no_workflow_in_zip": "kein ComfyUI-Workflow im Archiv",
        "msg_unsupported": "nicht unterstützte Dateiendung",
        "msg_dangerous_path": "gefährlicher Pfad im Archiv: {name}",
        "msg_too_large": "Archiv entpackt zu groß ({size:.1f} GB)",
        "msg_original_not_deleted": "die Originaldatei konnte nicht gelöscht werden: {error}",
        "msg_not_trashed": "das ZIP konnte nicht in den Papierkorb verschoben werden: {error}",
        "msg_download_unfinished": "Download nach {seconds:.0f} s nicht abgeschlossen",
        "msg_desktop_missing": "Desktop-Ordner nicht gefunden: {path}",
        "msg_shortcut_failed": "Verknüpfung konnte nicht erstellt werden",
    },
}

_current = DEFAULT_LANGUAGE


def set_language(code: str) -> None:
    """Switches the current language; unknown codes fall back to English."""
    global _current
    _current = code if code in TEXTS else DEFAULT_LANGUAGE


def get_language() -> str:
    return _current


def t(key: str, **values) -> str:
    """Text for `key` in the current language, with `values` filled in."""
    text = TEXTS[_current].get(key) or TEXTS[DEFAULT_LANGUAGE][key]
    return text.format(**values) if values else text


def root_labels() -> set[str]:
    """The "(root)" entry of the subfolder list, in every language."""
    return {texts["root_label"] for texts in TEXTS.values()}


def system_language() -> str:
    """Windows display language if supported, otherwise English."""
    try:
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except (AttributeError, OSError):
        return DEFAULT_LANGUAGE
    primary = lang_id & 0x3FF
    return {0x09: "en", 0x0C: "fr", 0x07: "de"}.get(primary, DEFAULT_LANGUAGE)
