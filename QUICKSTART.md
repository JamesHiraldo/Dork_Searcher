# Wayback Atlas quick start

In CMD, from the project directory:

```cmd
wayback_atlas.bat
```

Use menu **1** to discover hosts, **4** to check them, **5** to collect repeat
samples, and **10** to export the inventory.

Direct executable commands:

```cmd
Wayback_Atlas_App\wayback_atlas.exe discover example.com
Wayback_Atlas_App\wayback_atlas.exe check example.com
Wayback_Atlas_App\wayback_atlas.exe watch example.com --rounds 5 --interval 60
Wayback_Atlas_App\wayback_atlas.exe dorks example.com "ext:js OR path:/api/"
```

Outputs default to Desktop\Wayback_Atlas_Results. The SQLite inventory persists
between runs. Keep the terminal open while watching; Ctrl+C stops safely.

No-response observations are not proof that a hostname is permanently dead.
Use only on assets you own or have permission to assess.

See [README.md](README.md) for all flags, source requirements and result meanings.
