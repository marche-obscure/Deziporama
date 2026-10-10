<p align="center"><img src="assets/deziporama.webp" alt="Deziporama" width="420"></p>

# Deziporama

Deziporama files the ComfyUI workflows you download (for example from Discord) into your ComfyUI workflows folder, automatically.

Download a workflow `.json` or `.zip` as usual. A few seconds later it shows up in the subfolder you chose, extracted and tidied up, ready to open in ComfyUI.

Deziporama never connects to Discord. It only watches your Downloads folder, so your account is never at risk.

## Features

- **Watches your Downloads folder** and recognizes real ComfyUI workflows (UI and API formats). Other `.json` / `.zip` files are left alone.
- **Moves workflow `.json` files** into the chosen subfolder.
- **Extracts workflow `.zip` files**, then sends the zip to the Recycle Bin.
  - A zip that only holds one folder is extracted without a nested folder.
  - The `__MACOSX` folder is skipped.
  - The folder name is tidied: `EP33 WORKFLOWS` becomes `Ep33 Workflows`.
- **Never overwrites anything**: duplicates get a ` (2)`, ` (3)`… suffix.
- **Safe**: archives trying to write outside their folder are rejected, extraction is atomic, and there are size limits.
- **Stays out of the way**: minimizes to the notification area, can start at Windows sign-in, and only one copy runs at a time.
- **Desktop shortcut** offered on first launch, or available from a button later.
- **English, French and German**: chosen on first launch, changeable anytime from the banner.

## Requirements

- Windows 10 or 11.
- [Python 3](https://www.python.org/downloads/). During installation, tick **"Add Python to PATH"**.
- [Git](https://git-scm.com/download/win), only for the installation with Git (option 1 below).

## Installation

### Option 1: with Git

Open a **Command Prompt** (`cmd`) in the folder where you want Deziporama, then run:

```bat
git clone https://github.com/marche-obscure/Deziporama.git
cd Deziporama
"Start Deziporama.bat"
```

### Option 2: without Git

1. On this page, click **Code**, then **Download ZIP**.
2. Extract the zip anywhere on your PC.
3. Double-click **`Start Deziporama.bat`** in the extracted folder.

### First launch

The first launch creates a private Python environment (`.venv`) and installs the dependencies. This takes a minute and needs an Internet connection. Later launches are instant.

If the launcher reports an error, you can run the same steps by hand in a Command Prompt opened in the Deziporama folder:

```bat
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\pythonw.exe app.py
```

### Update

With Git, from the Deziporama folder:

```bat
git pull
```

Without Git, download the new zip and extract it over the old folder. Your settings (`config.json`) are kept.

On the first launch, Deziporama asks for your language (English, Français or Deutsch), then offers to create a desktop shortcut.
You can change the language later with the selector in the top-right corner of the banner.

## Usage

1. **Workflows folder**: click *Browse…* and pick your ComfyUI workflows folder, usually `ComfyUI\user\default\workflows`.
2. **Subfolder**: pick where downloads should go, or click *New…* to create one, for example one per Discord channel.
3. Click **Start**, then download workflows as usual.

The log shows each file:

| Color | Meaning |
|---|---|
| Green | Imported |
| Grey | Ignored (not a workflow) |
| Orange | Imported, with a warning |
| Red | Error |

After fixing an error (for example, a drive that was unplugged), click **Retry errors**.

### Options

- **Also process files already present when starting**: imports the workflows already sitting in Downloads when you click Start.
- **Start at Windows sign-in**: Deziporama starts minimized next to the clock, already watching.
- **Minimize** sends the window to the notification area. **Close** asks whether to minimize or quit.

## Development

```bash
.venv\Scripts\python -m pytest tests -q
```

The design document is in [`docs/superpowers/specs/2026-10-10-deziporama-design.md`](docs/superpowers/specs/2026-10-10-deziporama-design.md).

Settings are stored in `config.json`, next to `app.py`. This file is not versioned.

## License

The source code is released under the [MIT License](LICENSE).

The images in the `assets` folder (Deziporama logo and icon) are **not** covered by the
MIT License: © 2026 marche-obscure, all rights reserved. They may not be reused, modified or
redistributed separately from Deziporama without permission.
