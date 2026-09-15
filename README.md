# LinkedIn Content Engine — Codex Skill

Local-first LinkedIn identity and content engine. No LinkedIn API, no scraping, no auto-publishing.

## Windows install

1. Unzip the package.
2. Open PowerShell in the extracted folder.
3. Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\linkedin-content-engine\install.ps1
```

It installs the skill to `$HOME\.codex\skills\linkedin-content-engine` (or `$CODEX_HOME\skills\...` when `CODEX_HOME` is configured).

Restart Codex after installation.

## macOS / Linux install

```bash
./linkedin-content-engine/install.sh
```

Restart Codex after installation.

## Manual install

Copy the full `linkedin-content-engine` folder to:

```text
~/.codex/skills/linkedin-content-engine
```

## First use

Export your LinkedIn data, place the ZIP somewhere Codex can read it, then ask:

```text
Use $linkedin-content-engine. Ingest C:\ruta\linkedin-export.zip, build my identity model, and show me the key findings before drafting content.
```

Codex will create project-local state under:

```text
.linkedin-content-engine/
```

The installed skill itself remains generic. El Skill no envía datos directamente a LinkedIn ni a servicios propios. Los archivos permanecen en el proyecto, pero su contenido puede ser procesado por Codex cuando se utiliza para analizarlo o redactar contenido.

Messages and connections are excluded by default because they can contain third-party personal data. Keep `.linkedin-content-engine/` out of source control and shared folders.

## Read a visible profile

Codex can read one profile page visible in an available browser when you explicitly request it. This is a point-in-time, user-directed reading: it does not crawl LinkedIn, bypass authentication, or perform account actions. A visible profile alone is normally insufficient to build a reliable voice model.

## Evidence-backed content

Ask Codex to research a claim with scientific or professional sources before drafting. The skill records source scope and limitations, separates research findings from interpretation and personal experience, and includes direct citations in the returned draft.

## Direct parser usage

Windows:

```powershell
python "$HOME\.codex\skills\linkedin-content-engine\scripts\ingest_linkedin_export.py" "C:\ruta\linkedin-export.zip" --output .linkedin-content-engine
```

macOS/Linux:

```bash
python3 ~/.codex/skills/linkedin-content-engine/scripts/ingest_linkedin_export.py /path/linkedin-export.zip --output .linkedin-content-engine
```

To add new activity later without duplicating records, use `--append`.

Only after an explicit request to process messages or connections, add `--include-sensitive`. The parser enforces file, archive and record limits; inspect `--help` to adjust them deliberately.
