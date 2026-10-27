# Windows executable

Run `Wayback_Atlas_App/wayback_atlas.exe` or `wayback_atlas.bat` from the root.
The new executable supports interactive mode and CLI arguments:

```cmd
wayback_atlas.exe --help
wayback_atlas.exe discover example.com
wayback_atlas.exe watch example.com --rounds 6 --interval 120
```

Use PowerShell to check the checksum against `Wayback_Atlas_App/SHA256SUMS.txt`:

```powershell
Get-FileHash .\Wayback_Atlas_App\wayback_atlas.exe -Algorithm SHA256
```

No administrator privileges, browser runtime or packet driver are required.
Output goes to the resolved Desktop\Wayback_Atlas_Results directory by default.
Use `--output-dir PATH` before a command to override it.

Do not launch archived Dork Searcher 2.0 binaries under `legacy/` for current work.
See [README](../README.md) for all flags and status definitions.
