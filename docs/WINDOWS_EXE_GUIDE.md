# Windows executable

Run `Wayback_Atlas_App/wayback_atlas.exe` or `wayback_atlas.bat` from the root.
The new executable supports interactive mode and CLI arguments:

```cmd
Wayback_Atlas_App\wayback_atlas.exe --help
Wayback_Atlas_App\wayback_atlas.exe discover example.com
Wayback_Atlas_App\wayback_atlas.exe watch example.com --rounds 6 --interval 120
```

These commands run from the repository root in CMD. Prefix paths with `.\` in
PowerShell. Double-clicking the EXE opens the interactive dashboard. For error
diagnosis, launch it from an existing terminal so messages remain visible.

Use PowerShell to check the checksum against `Wayback_Atlas_App/SHA256SUMS.txt`:

```powershell
Get-FileHash .\Wayback_Atlas_App\wayback_atlas.exe -Algorithm SHA256
```

Compare the displayed digest to the matching filename in the checksum file.
Checksums detect changed bytes; they are not a publisher signature. This release
is not Authenticode-signed. Follow your organization's application policy; do not
disable endpoint protection to run it.

No administrator privileges, browser runtime or packet driver are required.
Output goes to the resolved Desktop\Wayback_Atlas_Results directory by default.
Use `--output-dir PATH` before a command to override it.

Obsolete Dork Searcher 2.0 binaries have been removed from the working folder.
The old `dork_searcher.bat` name is only a compatibility launcher for Atlas.
The EXE is a self-contained Windows build; Linux/macOS use the Python installation.
Source edits do not update this EXE automatically. See [development](DEVELOPMENT.md)
to rebuild it. This documentation-only update does not replace the existing binaries.
See [README](../README.md) for all flags and status definitions.
