# setup.py — do NOT import the package here.
from setuptools import setup, find_packages
from pathlib import Path

# Single source of truth for version — change as needed
VERSION = "0.2.0"

README = Path(__file__).with_name("README.md")
long_description = README.read_text(encoding="utf-8") if README.exists() else ""

setup(
    name="warranty",
    version=VERSION,
    description="Warranty plugin for InvenTree (SafetyCulture sync)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Derek Huang",
    author_email="2002derekh@gmail.com",
    url="https://github.com/huangderek02/inventree-warranty",
    packages=find_packages(exclude=("tests", "docs")),
    include_package_data=True,
    python_requires=">=3.10",
    install_requires=[
        "requests>=2.31.0",
        "python-dateutil>=2.8.2",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Framework :: Django",
    ],
)
