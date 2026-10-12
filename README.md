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
- **Pixaroma episodes**: list the free episodes of [workflows.pixaroma.com](https://workflows.pixaroma.com/), see which ones are new, imported or missing, and import them in one click into folders named `Ep## - Title`, from the window or straight from the notification area.
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

1. Click the **⚙** icon in the banner to open the settings:
   - **Watched folder**: your Downloads folder (set by default).
   - **Workflows folder**: your ComfyUI workflows folder, usually `ComfyUI\user\default\workflows`.
   - **Subfolder**: where downloads should go; *New…* creates one, for example one per Discord channel.
   - **Pixaroma folder** and **Pixaroma subfolder**: where Pixaroma episodes are imported, for example one subfolder per year.

   While watching is running, the watched and workflows folders are locked: the settings window offers a **Stop watching** button, and asks whether to restart watching when you click **OK**.
2. Click **Start**, then download workflows as usual.
3. Click **Pixaroma** to list the Pixaroma episodes (see [Pixaroma](#pixaroma) below).

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
- **Check for new Pixaroma episodes at start**: a line in the log tells you when new episodes are out.
- **Minimize** sends the window to the notification area. **Close** asks whether to minimize or quit.

## Pixaroma

Deziporama reads the free episode list and ZIP files from [workflows.pixaroma.com](https://workflows.pixaroma.com/), only when you ask for it (or once at start if the option is ticked). It never polls the site in the background.

### Episode window

The **Pixaroma** button lists every episode, newest first, with its category, number of workflows, size and status:

| Status | Meaning |
|---|---|
| Imported | An `Ep## - Title` folder exists in the Pixaroma folder or one of its subfolders |
| New | Released since you last opened the list |
| Not imported | Not on your disk |
| Coming soon – not imported | Announced on the site, not on your disk |
| Ignored | Marked *Don't offer again* |

Select one or more episodes, then click **Import selected**. Double-click an episode to watch its video. **Don't offer again** and **Offer again** act on the selected episodes.

### From the notification area

Right-click the Deziporama icon next to the clock, then choose **Pixaroma**. Deziporama checks the site without opening its window and offers:

- the new episodes;
- the episodes it imported earlier and that you have deleted since;
- but never the episodes marked *Don't offer again*.

Choose **Download**, **Later** or **Don't offer again**. While downloading, a small window shows the episode, the step (downloading, then extracting) and a progress bar. When everything is extracted and renamed, a **Pixaroma workflows available** window lists the new folders.

### About the Pixaroma name and content

Deziporama is an **independent, unofficial** project. It is **not affiliated with, endorsed by or sponsored by Pixaroma**.

"Pixaroma" is the name used by its creator for the YouTube channel, the websites ([pixaroma.com](https://pixaroma.com/), [workflows.pixaroma.com](https://workflows.pixaroma.com/)) and the shop, and it may be a trademark of its owner. Deziporama uses it only to say which site it works with.

What applies to the content, as far as the Pixaroma sites state it (October 2026):

- **Workflows and episode files**: offered as free downloads on workflows.pixaroma.com. No license is stated for them, so they remain the property of their author, all rights reserved.
- **Pixaroma nodes** ([ComfyUI-Pixaroma](https://github.com/pixaroma/ComfyUI-Pixaroma)): MIT license, which allows use, copy, modification and sharing as long as the copyright notice is kept.
- **Shop**: its [Terms of Service](https://shop.pixaroma.com/pages/terms-of-service) state that its materials belong to the creator and forbid claiming a false affiliation.

Deziporama does not host, copy or redistribute any Pixaroma file. Every ZIP is downloaded from the official site, exactly as when you click *Download* yourself, and only when you ask for it.

**Recommended use:**

- Use the downloaded workflows for your own work.
- Do not re-upload, share, bundle or sell the workflows or ZIP files without the author's permission.
- Keep the credits and notices that come with the files.
- Do not present Deziporama, or anything made with it, as an official Pixaroma product.
- Support the creator: watch the [videos](https://www.youtube.com/@pixaroma), join the [Discord](https://discord.gg/gggpkVgBf3), or use the [shop and donations](https://shop.pixaroma.com/).

If you are the owner of Pixaroma and want the name, the logo or this feature changed or removed, please [open an issue](https://github.com/marche-obscure/Deziporama/issues). It will be done.

*This section is information, not legal advice.*

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
