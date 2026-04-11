# -*- coding: utf-8 -*-
"""
Shared string utility functions for FG-Tools scripts.
"""

import re


def safe_string(value):
    """Convert value to a stripped string; returns '' on None or error."""
    try:
        return "{}".format(value or "").strip()
    except Exception:
        return ""


def normalize(value):
    """Return upper-case stripped string for case-insensitive comparison."""
    return safe_string(value).upper()


def normalize_whitespace(value):
    """Collapse internal whitespace and upper-case for comparison."""
    return re.sub(r"\s+", " ", safe_string(value)).upper()
