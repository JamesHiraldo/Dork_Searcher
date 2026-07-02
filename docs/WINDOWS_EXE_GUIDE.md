# Windows Executable Quick Start Guide

**For users who received `dork_searcher.exe` - No Python needed!**

---

## 🚀 Getting Started (30 seconds)

### Option 1: Simple Double-Click (Easiest)
1. Find `dork_searcher.exe` file
2. **Double-click** it
3. A command window will open with an interactive menu
4. Select an option and follow the prompts

### Option 2: Create a Desktop Shortcut (Convenient)
1. Right-click `dork_searcher.exe`
2. Select **"Create shortcut"** or **"Send to → Desktop (create shortcut)"**
3. You can now launch from your desktop anytime

---

## 📋 What You Can Do

The application provides passive reconnaissance tools:

- **Google CSE Search** - Search with your Google API
- **Wayback Machine** - Find archived versions of websites
- **DuckDuckGo** - Search without API
- **Dogpile** - Attempts Dogpile first, then falls back to browser-rendered Brave results when needed
- **Subdomain Finder** - Discover subdomains
- **DNSDumpster** - DNS and attack-surface lookup with API key
- **Passive Probing** - Check security headers
- **Recon Pipeline** - Run multiple searches at once

---

## ⚙️ System Requirements

✓ **Windows 7, 8, 10, 11** (64-bit)  
✓ **Internet connection** (for external API calls)  
✓ **No Python required** - Everything is built-in  
✓ **No installation** - Just run the exe!

---

## ⚠️ Common Questions

### Q: "Windows protected your PC" message?
**A:** This is normal for new unsigned executables.
- Click "More info" 
- Click "Run anyway"
- The app is safe to run

### Q: Where should I keep the exe?
**A:** Any permanent location works:
- `C:\Program Files\dork_searcher\`
- `C:\Users\YourName\Tools\`
- Your Desktop
- USB drive (it's portable!)

### Q: Can I move or copy the exe to another computer?
**A:** Yes! It's completely portable. Just copy `dork_searcher.exe` to any Windows 64-bit computer.

### Q: Does it work offline?
**A:** No, it needs internet to connect to external search APIs and services.

### Q: How do I provide API keys?
**A:** When you select a search option that needs an API key, you'll be prompted for input:
- For sensitive keys like Google API keys, input will be **hidden** (you won't see typing)
- Copy-paste works if typing feels unreliable
- DNSDumpster requires an API key; Dogpile does not use one

### Q: Can I run it from Command Prompt?
**A:** Yes!
```cmd
C:\Path\To\dork_searcher.exe
```

---

## 📁 Output Files

Results are saved to a **`Result/`** folder:
- **JSON format** - Always available (recommended for data analysis)
- **CSV format** - Optional (for spreadsheet apps like Excel)

Check the `Result/` folder for your findings!

---

## 🔧 Updating

**To get the latest version:**
1. Download the newest `dork_searcher.exe` from your distributor
2. Replace the old exe file with the new one
3. Your settings and output folders remain unchanged

---

## 📞 Troubleshooting

| Problem | Solution |
|---------|----------|
| Exe won't start | Make sure Windows is 64-bit; try running as Administrator |
| "File not found" errors | Don't run from Temp folder - keep exe in permanent location |
| API errors | Check internet connection and verify your API keys |
| Can't see my output | Look in the `Result/` folder in your current directory |
| Window closes too fast | Run from Command Prompt instead: `cmd.exe` → type the exe path |

---

## ✨ Tips & Tricks

- **First time using?** Try DuckDuckGo search - no API key needed!
- **Dogpile fallback** - If Dogpile only shows a loading shell, the app automatically uses Brave search results instead
- **Bulk operations** - Use the Recon Pipeline to run multiple searches
- **Export results** - Save to CSV to analyze in Excel
- **High rate limits** - If getting blocked, increase the rate delay in settings
- **API-free searches** - Wayback Machine and DuckDuckGo don't require keys

---

**Questions or issues?** Contact your distributor or check the main README.md file.
