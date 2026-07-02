#!/usr/bin/env python3
from setuptools import setup, find_packages
from pathlib import Path

root_dir = Path(__file__).parent.parent
with open(root_dir / "docs" / "README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="dork-searcher",
    version="1.0.0",
    author="Maydayx2",
    description="API-based Dork Searcher with interactive CLI menu for passive reconnaissance",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/dork-searcher",
    packages=find_packages(where="../src"),
    package_dir={"": "../src"},
    entry_points={
        'console_scripts': [
            'dork_searcher=cli:main',
        ],
    },
    install_requires=[
        'requests>=2.28.0',
        'python-dateutil>=2.8.0',
        'httpx>=0.24.0',
        'playwright>=1.54.0',
    ],
    python_requires='>=3.8',
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
