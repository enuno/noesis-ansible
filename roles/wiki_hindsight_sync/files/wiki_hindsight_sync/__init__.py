"""One-way sync from the llm-wiki into a Hindsight memory bank.

The wiki is the canonical, editable source. Hindsight holds a reviewed
subset of it, with provenance. Nothing in this package writes to the wiki
or deletes anything remotely.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
