# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
# import os
# import sys
# sys.path.insert(0, os.path.abspath('.'))


# -- Project information -----------------------------------------------------

project = 'DvG_QDeviceIO'
copyright = '2021, Dennis van Gils'
author = 'Dennis van Gils'

# The full version, including alpha/beta/rc tags
release = '0.4.0'

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.intersphinx',
    'sphinx_qt_documentation',
]

intersphinx_mapping = {
    'PyQt5': ('https://www.riverbankcomputing.com/static/Docs/PyQt5/', None),
    'NumPy': ('https://numpy.org/doc/stable/', None),
    'python': ('https://docs.python.org/3', None)
}

qt_documentation = 'Qt5'

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']


master_doc = 'index'

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
# 'bizstyle', 'classic', 'sphinx_rtd_theme'
html_theme = 'sphinx_rtd_theme'

html_theme_path = ["_themes", ]
#html_theme_options = {
#    'canonical_url': '',
#    'analytics_id': 'UA-XXXXXXX-1',  #  Provided by Google in your dashboard
#    'logo_only': False,
#    'display_version': True,
#    'prev_next_buttons_location': 'bottom',
#    'style_external_links': False,
#    'style_nav_header_background': '#2980B9',
# Toc options
#    'collapse_navigation': True,
#    'sticky_navigation': True,
#    'navigation_depth': 4,
#    'includehidden': True,
#    'titles_only': False
#}

html_last_updated_fmt = '%d-%m-%Y'
html4_writer = True

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
#html_static_path = ['_static']

# Napoleon settings
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False    # True to create block. Downside is that we lose hyperlinks to class variables
napoleon_use_param = False  # False
napoleon_use_rtype = True