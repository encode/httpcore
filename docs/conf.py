# See: https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --

import os
import sys

# Allow sphinx-autodoc to access `httpcore` contents.
sys.path.insert(0, os.path.abspath("."))

# -- Project information --

project = "HTTPCore"
copyright = "2021, Encode"
author = "Encode"

# -- General configuration --

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "sphinx_autodoc_typehints",
]

myst_enable_extensions = [
    "colon_fence",
]

autodoc_member_order = "bysource"  # Preserve :members: order.

# -- HTML configuration --

html_theme = "furo"
