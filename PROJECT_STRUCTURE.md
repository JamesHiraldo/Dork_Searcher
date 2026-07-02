# 📁 Project Structure

```
dork_searcher/
├── 📂 src/                          # Source Code (Main Application)
│   ├── __init__.py                  # Package initialization
│   ├── cli.py                       # Interactive CLI menu interface
│   ├── dork_searcher.py             # Main entry point
│   ├── searcher.py                  # Core search functionality (Google, Wayback, etc.)
│   ├── passive_probe.py             # Security header probing & analysis
│   └── recon_pipeline.py            # Multi-stage reconnaissance workflows
│
├── 📂 config/                       # Configuration & Setup Files
│   ├── setup.py                     # Setuptools configuration (legacy)
│   ├── pyproject.toml               # Modern Python project metadata & build config
│   ├── requirements.txt             # Pip dependency list
│   └── dork_searcher.spec           # PyInstaller build specification (generated)
│
├── 📂 docs/                         # Documentation
│   ├── README.md                    # Main project documentation
│   ├── README_RECON.md              # Detailed recon techniques guide
│   ├── INSTALL.md                   # Installation & usage guide
│   └── WINDOWS_EXE_GUIDE.md         # Windows executable setup for end-users
│
├── 📂 dist/                         # Compiled Windows Executable
│   └── dork_searcher.exe            # Standalone Windows executable (no Python needed)
│
├── 📂 build/                        # Build Artifacts (Auto-generated)
│   └── [PyInstaller output files]
│
├── 📂 .venv/                        # Virtual Environment (Dev only)
│   └── [Python packages]
│
├── .gitattributes                   # Git configuration
├── dork_searcher.bat                # Windows batch launcher script
└── PROJECT_STRUCTURE.md             # This file - Documentation structure guide

```

---

## 📋 Folder & File Guide

### **`src/` - Source Code**
The main application code. All Python modules live here.

| File | Purpose |
|------|---------|
| `cli.py` | Interactive menu system for user interaction |
| `dork_searcher.py` | Entry point; runs the main application |
| `searcher.py` | Core search engine (Google CSE, Wayback, DuckDuckGo, Dogpile/Brave fallback, DNSDumpster, C99) |
| `passive_probe.py` | Security analysis (headers, CSP, CORS checking) |
| `recon_pipeline.py` | Advanced multi-step reconnaissance workflows |

**Usage:** `python -m src.cli` or `dork_searcher` (if installed)

---

### **`config/` - Configuration Files**
Setup and dependency management files.

| File | Purpose |
|------|---------|
| `pyproject.toml` | **Primary config** - Modern Python packaging (recommended) |
| `setup.py` | Legacy setup - kept for backward compatibility |
| `requirements.txt` | Package dependencies for pip install |
| `dork_searcher.spec` | PyInstaller config (generated when building exe) |

**Usage:** 
- `pip install -r config/requirements.txt` (install dependencies)
- `python -m pip install -e .` (install from config files)

---

### **`docs/` - Documentation**
User-facing guides and technical documentation.

| File | Purpose | Audience |
|------|---------|----------|
| `README.md` | Project overview & features | Everyone |
| `INSTALL.md` | Installation & troubleshooting guide | Developers |
| `README_RECON.md` | Advanced reconnaissance techniques | Security professionals |
| `WINDOWS_EXE_GUIDE.md` | End-user guide for Windows exe | Windows users (no tech needed) |

**Quick Links:**
- `📖 Getting started?` → Read `docs/README.md`
- `💻 Installing from source?` → Read `docs/INSTALL.md`
- `🪟 Using the Windows exe?` → Read `docs/WINDOWS_EXE_GUIDE.md`
- `🔍 Advanced techniques?` → Read `docs/README_RECON.md`

---

### **`dist/` - Executable & Release Files**
Pre-built, ready-to-run files.

| File | Purpose |
|------|---------|
| `dork_searcher.exe` | Standalone Windows executable (no Python required) |

**How to build:**
```powershell
python -m PyInstaller --onefile --name dork_searcher src/cli.py
```

---

### **`build/` - Build Artifacts**
Auto-generated files from PyInstaller. Safe to delete.

---

### **Root Level**

| File | Purpose |
|------|---------|
| `dork_searcher.bat` | Windows batch file to launch the application |
| `.gitattributes` | Git configuration for line endings |

---

## 🚀 Quick Commands

### Installation (Windows PowerShell)
```powershell
# Install from source
pip install -r config/requirements.txt
python -m playwright install chromium
pip install -e .

# Or run directly
python -m src.cli
```

### Building Windows Executable
```powershell
python -m PyInstaller --onefile --name dork_searcher src/cli.py
# Output: dist/dork_searcher.exe
```

### Running the Application

**From source:**
```powershell
python -m src.cli
```

**Pre-built executable:**
```powershell
dist/dork_searcher.exe
```

**Using batch file:**
```powershell
dork_searcher.bat
```

---

## 📦 What to Share/Distribute

### **For GitHub/Development:**
```
dork_searcher/
├── src/
├── config/
├── docs/
├── dork_searcher.bat
├── .gitattributes
└── [other project files]
```

### **For End-Users (Windows):**
- Just the `dist/dork_searcher.exe` file
- Include `docs/WINDOWS_EXE_GUIDE.md`
- (No Python installation needed!)

### **For Python Package Distribution (PyPI):**
- Everything EXCEPT: `.venv/`, `build/`, `dist/` (mostly)
- The `config/` files handle the rest

---

## 🔄 Development Workflow

```
1. Edit code → src/*.py
2. Test locally → python -m src.cli
3. Build exe → python -m PyInstaller ...
4. Check dist/ → dork_searcher.exe
5. Share or push to GitHub
```

---

## 💡 Tips

- ✅ Keep all Python code in `src/`
- ✅ Keep all docs in `docs/`
- ✅ Keep all config in `config/`
- ✅ Generated files? Don't worry - they auto-generate
- ✅ New dependencies? Add to `config/requirements.txt`
- ✅ Updating docs? Put them in `docs/`

---

**Last Updated:** June 29, 2026  
**Project:** Dork Searcher - Passive Reconnaissance Tool
