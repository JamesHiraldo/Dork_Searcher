#!/usr/bin/env python3
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="dork-searcher",
    version="1.0.0",
    author="Your Name",
    description="API-based Dork Searcher with interactive CLI menu",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/dork-searcher",
    packages=find_packages(),
    py_modules=['searcher', 'cli'],
    entry_points={
        'console_scripts': [
            'dork_searcher=cli:main',
        ],
    },
    install_requires=[
        'requests>=2.28.0',
        'python-dateutil>=2.8.0',
        'httpx>=0.24.0',
    ],
    python_requires='>=3.8',
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
