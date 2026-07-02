Recon pipeline (Wayback)

`recon_pipeline.py` queries the Internet Archive (CDX) for historical URLs and extracts query parameters and endpoints. It outputs a JSON summary and optional CSV listing.

Example:

```powershell
python -m src.recon_pipeline --targets t-mobile.com account.t-mobile.com --output c:\temp\recon.json --csv c:\temp\recon.csv
```

Notes:
- Passive-only: the script queries public archives and will not scan live hosts.
- Use the `--rate` flag to increase delay between CDX requests.
