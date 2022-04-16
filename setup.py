#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
from pathlib import Path

from setuptools import setup


def get_version(package):
    """
    Return package version as listed in `__version__` in `init.py`.
    """
    version = Path(package, "__init__.py").read_text()
    return re.search("__version__ = ['\"]([^'\"]+)['\"]", version).group(1)


def get_long_description():
    """
    Return the README.
    """
    long_description = ""
    with open("README.md", encoding="utf8") as f:
        long_description += f.read()
    long_description += "\n\n"
    with open("CHANGELOG.md", encoding="utf8") as f:
        long_description += f.read()
    return long_description


def get_packages(package):
    """
    Return root package and all sub-packages.
    """
    return [str(path.parent) for path in Path(package).glob("**/__init__.py")]


setup(
    name="httpcore",
    python_requires=">=3.7",
    version=get_version("httpcore"),
    url="https://github.com/encode/httpcore",
    project_urls={
        "Documentation": "https://www.encode.io/httpcore",
        "Source": "https://github.com/encode/httpcore",
    },
    license="BSD",
    description="A minimal low-level HTTP client.",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    author="Tom Christie",
    author_email="tom@tomchristie.com",
    packages=get_packages("httpcore"),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "h11>=0.11,<0.13",
        "sniffio==1.*",
        "anyio==3.*",
        "certifi",
    ],
    extras_require={
        "http2": ["h2>=3,<5"],
        "socks": ["socksio==1.*"]
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Topic :: Internet :: WWW/HTTP",
        "Framework :: AsyncIO",
        "Framework :: Trio",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3 :: Only",
    ],
)
