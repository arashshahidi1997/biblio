"""Knowledge wiki toolkit: scaffold, lint, generated views and status.

The method (principles, page types, lifecycle) follows the wiki specification;
see docs/explanation/wiki.md. Everything here is deterministic and edits only
plain files, so Obsidian or VS Code stays the place where people read and review.
"""
from .schema import WikiConfig, load_wiki_config

__all__ = ["WikiConfig", "load_wiki_config"]
