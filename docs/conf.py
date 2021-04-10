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
]

myst_enable_extensions = [
    "colon_fence",
]

# Preserve :members: order.
autodoc_member_order = "bysource"

# Show type hints in descriptions, rather than signatures.
autodoc_typehints = "description"

# -- HTML configuration --

html_theme = "furo"

# -- Internationalization --
# https://www.sphinx-doc.org/en/master/usage/advanced/intl.html

locale_dirs = ['locale/']
gettext_compact = False

# -- App setup --


def _viewcode_follow_imported(app, modname, attribute):
    # We set `__module__ = "httpcore"` on all public attributes for prettier
    # repr(), so viewcode needs a little help to find the original source modules.

    if modname != "httpcore":
        return None

    import httpcore

    try:
        # Set in httpcore/__init__.py
        return getattr(httpcore, attribute).__source_module__
    except AttributeError:
        return None


def setup(app):
    app.connect("viewcode-follow-imported", _viewcode_follow_imported)
