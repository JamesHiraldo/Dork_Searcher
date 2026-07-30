# Windows executable guide

The executable is a console application for authorized reconnaissance. Interactive
reports are saved under `Desktop\Dork_Searcher_Results` by default.

```powershell
.\dork_searcher.exe
```

Before trusting a distributed executable, compare its SHA-256 value with the release
publisher's checksum:

```powershell
Get-FileHash .\dork_searcher.exe -Algorithm SHA256
```

The executable provides Google, DuckDuckGo, Wayback, Certificate Transparency,
DNSDumpster, cross-reference, archive analysis, and active HTTP metadata workflows.
Google and DNSDumpster require API credentials. Key input is hidden.

DuckDuckGo is the primary web-search provider and automatically falls back to
Dogpile. The browser-rendered Brave final fallback is not bundled in the base
executable. All other core workflows remain available without a browser installation.

The interactive menu uses color in supported terminals. Set `NO_COLOR=1` before
launching to force plain output.

The program resolves the actual Windows Desktop path, including OneDrive or localized
folder redirection. If it is not writable, the application automatically uses
`%LOCALAPPDATA%\Dork_Searcher\Results` instead. Option 10 manages persistent custom
dorks stored in the same easy-to-find results folder.

Important operational rules:

- Use only targets explicitly authorized by a bug bounty program or owner.
- Treat option 8 as active testing; it sends bodyless GET requests.
- Keep result artifacts private because archive URLs can contain sensitive values.
- Replace the executable with every release rather than mixing old binaries and new
  source files.
