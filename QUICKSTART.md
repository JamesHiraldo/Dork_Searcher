# Wayback Atlas quick start

In CMD, from the project directory:

```cmd
wayback_atlas.bat
```

In PowerShell: `.\wayback_atlas.bat`. No Python or administrator elevation is
required for the supplied EXE. Use your own authorized target in place of `example.com`.

Use menu **1** to discover hosts, **4** to check them, **5** to collect repeat
samples, and **10** to export the inventory.

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
```

Place `--output-dir` before the subcommand. Inspect the discovered list before
selecting HTTP checks. `watch` checks the stored list from startup; repeat
`discover` separately to find newly observed hosts. No schedule is installed.

Outputs default to Desktop\Wayback_Atlas_Results. The SQLite inventory persists
between runs. Keep the terminal open while watching; Ctrl+C stops safely.

No-response observations are not proof that a hostname is permanently dead.
Use only on assets you own or have permission to assess.

See [README.md](README.md) for all flags, source requirements and result meanings.
See [operations](docs/OPERATIONS.md) for imports, backup, exit codes and errors.
