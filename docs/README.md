# Wayback Atlas documentation

Dork Searcher has become **Wayback Atlas 3.2**. The canonical guide is
[the root README](../README.md), including Windows CMD startup, every command/flag,
the terminal menu, API setup, offline archive dorks, monitoring and export semantics.

Google, Dogpile and Playwright were removed, along with obsolete 2.0 binaries.
Previous tracked releases remain in Git history. Use `wayback_atlas.bat` or
`Wayback_Atlas_App/wayback_atlas.exe`.

The parameter-inventory module remains documented in [README_RECON.md](README_RECON.md).

## Documentation map

| Need | Guide |
| --- | --- |
| First run and terminal menu | [Quick start](../QUICKSTART.md) |
| Commands, flags, providers and state labels | [Main README](../README.md) |
| Source, wheel or EXE installation | [Install](INSTALL.md) |
| Windows paths, checksums and release behavior | [Windows EXE](WINDOWS_EXE_GUIDE.md) |
| Imports, data model, backup, automation and errors | [Operations](OPERATIONS.md) |
| Checkpoints, resume and Common Crawl selection | [Resumable discovery](RESUMABLE_DISCOVERY.md) |
| Legacy parameter analysis and HTTP/CORS command | [Retained commands](README_RECON.md) |
| Tests, packaging and release verification | [Development](DEVELOPMENT.md) |
| Current limitations and prioritized add-ons | [Assessment and roadmap](ASSESSMENT_AND_ROADMAP.md) |
| Implemented fixes and new features | [Release notes](RELEASE_NOTES.md) |
| Code and generated-file layout | [Project structure](../PROJECT_STRUCTURE.md) |
| Vulnerability reporting and repository policy | [Security policy](../SECURITY.md) |

The roadmap contains proposals, not additional working commands. Documentation
describes Atlas 3.2.0; the project is beta. Providers can change independently of
the application. A successful local test does not guarantee provider availability.
