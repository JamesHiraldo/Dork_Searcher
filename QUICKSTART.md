# 🚀 Dork Searcher - Quick Start

## 📁 Project Organization

```
dork_searcher/
├── 📂 src/              ← All Python source code here
├── 📂 docs/             ← All documentation here  
├── 📂 config/           ← Setup & configuration files
├── 📂 dist/             ← Windows executable (dork_searcher.exe)
├── 📄 PROJECT_STRUCTURE.md   ← Full folder guide
└── 📄 dork_searcher.bat      ← Windows launcher
```

---

## ⚡ Quick Commands

### **Windows Users - Easiest Way**
```powershell
# Just run the exe!
.\dist\dork_searcher.exe
```

### **Developers - Run from Source**
```powershell
# Install dependencies
pip install -r config/requirements.txt

# Run the app
python src/dork_searcher.py
```

### **Build Windows Executable**
```powershell
python -m PyInstaller --onefile --name dork_searcher src/cli.py
```

---

## 📚 Documentation

| File | For |
|------|-----|
| **[docs/README.md](docs/README.md)** | Overview & features |
| **[docs/INSTALL.md](docs/INSTALL.md)** | Installation guide |
| **[docs/WINDOWS_EXE_GUIDE.md](docs/WINDOWS_EXE_GUIDE.md)** | Windows exe setup (non-techies) |
| **[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)** | Detailed folder structure |

---

## 🎯 Common Tasks

### Install & Run from Source
```powershell
pip install -r config/requirements.txt
python src/dork_searcher.py
```

### Install Globally (Windows)
```powershell
pip install -e .
dork_searcher  # Now available from anywhere!
```

### Add to PATH (Windows)
1. Copy `dork_searcher.bat` to `C:\Windows\System32`
2. Run from anywhere: `dork_searcher`

### Share with Others
- **No Python?** → Send `dist/dork_searcher.exe` + `docs/WINDOWS_EXE_GUIDE.md`
- **Python available?** → Send everything except `/dist` and `/build`
- **For GitHub?** → Commit everything (ignore `.venv/`, `build/`)

---

## 📦 Files at a Glance

### **src/** - Application Code
- `cli.py` - User interface menu
- `searcher.py` - Search engine core
- `passive_probe.py` - Security analysis
- `recon_pipeline.py` - Advanced workflows

### **config/** - Setup Files
- `pyproject.toml` - Modern Python packaging
- `setup.py` - Legacy setup (backup)
- `requirements.txt` - Python dependencies
- `dork_searcher.spec` - PyInstaller config

### **docs/** - User Documentation
- `README.md` - Main project info
- `INSTALL.md` - Detailed installation
- `README_RECON.md` - Advanced techniques
- `WINDOWS_EXE_GUIDE.md` - Windows exe guide

### **dist/** - Distributions
- `dork_searcher.exe` - Standalone Windows executable

---

## 🔄 Workflow

```
📝 Code Changes
    ↓
🧪 Test Locally (python src/dork_searcher.py)
    ↓
🏗️ Build Exe (PyInstaller)
    ↓
✅ Test Exe (dist/dork_searcher.exe)
    ↓
📤 Distribute / Commit to GitHub
```

---

## 💡 Pro Tips

✅ All Python code stays in `src/`  
✅ All docs stay in `docs/`  
✅ All configs stay in `config/`  
✅ Run `git add . && git commit -m "message"` to backup (ignores .venv/build/)  
✅ Generated files are safe to delete and will regenerate  

---

## 🆘 Need Help?

1. **Run the app?** → See [docs/WINDOWS_EXE_GUIDE.md](docs/WINDOWS_EXE_GUIDE.md) (for exe) or [docs/INSTALL.md](docs/INSTALL.md) (for source)
2. **Understand structure?** → Read [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)
3. **Advanced techniques?** → Check [docs/README_RECON.md](docs/README_RECON.md)

---

**Version:** 1.0.0  
**Last Updated:** June 29, 2026  
**Status:** ✅ Organized & Ready
