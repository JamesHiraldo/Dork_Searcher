"""
Dork Searcher - Passive Reconnaissance Tool
API-based Dork Searcher with interactive CLI menu for finding subdomains and endpoints
"""

__version__ = "1.0.0"
__author__ = "Maydayx2"
__description__ = "Passive Recon Tool - Dorker Searcher & Subdomain/Endpoint Finder"

from .cli import main

__all__ = ['main']
