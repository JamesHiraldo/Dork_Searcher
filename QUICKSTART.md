# Wayback Atlas quick start

In CMD, from the project directory:

```cmd
wayback_atlas.bat
```

In PowerShell: `.\wayback_atlas.bat`. No Python or administrator elevation is
required for the supplied EXE. Use your own authorized target in place of `example.com`.

Use menu **1** to discover hosts, **4** to check them, **5** to collect repeat
samples, and **10** to export the inventory.
Type the number and press Enter. Choose **0** to exit; submenus use **0** to go
back. Start with the left-hand Discover & Check group, then use Your Workspace
for imports, local dorks and exports. In narrow windows the groups stack vertically.
Menu **11** provides local diagnostics and a full database backup.
Menu **12** resumes interrupted or budget-limited discoveries. Common Crawl is included
in menu 1; select it alone from menu 3. It searches archive indexes, not live site content.

Direct executable commands:

```cmd
Wayback_Atlas_App\wayback_atlas.exe discover example.com
Wayback_Atlas_App\wayback_atlas.exe check example.com
Wayback_Atlas_App\wayback_atlas.exe watch example.com --rounds 5 --interval 60
Wayback_Atlas_App\wayback_atlas.exe dorks example.com "ext:js OR path:/api/"
```

Use a dedicated results folder consistently across commands:

```cmd
wayback_atlas.bat --output-dir "D:\Recon\Example" discover example.com
wayback_atlas.bat --output-dir "D:\Recon\Example" inventory example.com
wayback_atlas.bat --output-dir "D:\Recon\Example" check example.com --dns-only
wayback_atlas.bat --output-dir "D:\Recon\Example" export example.com
wayback_atlas.bat --output-dir "D:\Recon\Example" doctor
wayback_atlas.bat --output-dir "D:\Recon\Example" backup "D:\Recon\Example-backup.sqlite3"
```

Use a new backup filename each time; existing files are never overwritten.
Run `wayback_atlas.bat --version` to confirm you are using 3.2.0.

Continue a saved run (replace `RUN_ID` with the full ID shown by `runs`):

```cmd
wayback_atlas.bat --output-dir "D:\Recon\Example" runs
wayback_atlas.bat --output-dir "D:\Recon\Example" resume RUN_ID --limit 10000 --max-pages 50
```

`discover` always starts a fresh query; `resume` continues an existing query. See
[resumable discovery](docs/RESUMABLE_DISCOVERY.md) for Common Crawl index selection and recovery.

Place `--output-dir` before the subcommand. Inspect the discovered list before
selecting HTTP checks. `watch` checks the stored list from startup; repeat
`discover` separately to find newly observed hosts. No schedule is installed.

Outputs default to Desktop\Wayback_Atlas_Results. The SQLite inventory persists
between runs. Keep the terminal open while watching; Ctrl+C stops safely.

No-response observations are not proof that a hostname is permanently dead.
Use only on assets you own or have permission to assess.

See [README.md](README.md) for all flags, source requirements and result meanings.
See [operations](docs/OPERATIONS.md) for imports, backup, exit codes and errors.
