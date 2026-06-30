#!/usr/bin/env python3
"""
Dork Searcher Wrapper - Quick start script
This is an alternative entry point that can be used directly
"""
import sys
import os

# Add the current directory to path so we can import searcher
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli import main

if __name__ == '__main__':
    main()
