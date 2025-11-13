# setup.py — do NOT import the package here.
from setuptools import setup, find_packages
from pathlib import Path
from warranty import PLUGIN_VERSION

# Single source of truth for version — change as needed
VERSION = "0.2.0"

README = Path(__file__).with_name("README.md")
long_description = README.read_text(encoding="utf-8") if README.exists() else ""

setup(
    name="warranty",
    version=PLUGIN_VERSION,   # <-- ensure this uses PLUGIN_VERSION
    packages=find_packages(),
    install_requires=[
        "requests",
        "python-dateutil",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Framework :: Django",
    ],
)

