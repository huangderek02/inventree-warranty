from setuptools import setup, find_packages
from pathlib import Path

# Single source of truth for version — change as needed
VERSION = "0.2.0"

README = Path(__file__).with_name("README.md")
long_description = README.read_text(encoding="utf-8") if README.exists() else ""

setup(
    name="warranty",
    version=VERSION,  # <-- use the constant here
    packages=find_packages(),
    install_requires=[
        "requests",
        "python-dateutil",
    ],
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Framework :: Django",
    ],
)
