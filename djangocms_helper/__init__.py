# -*- coding: utf-8 -*-
"""djangocms-helper - Helpers for django CMS plugin development"""
from __future__ import absolute_import, print_function, unicode_literals

# make sure bar is in sys.modules
import app_helper  # NOQA
# link this module to bar
sys.modules[__name__] = sys.modules['app_helper']
