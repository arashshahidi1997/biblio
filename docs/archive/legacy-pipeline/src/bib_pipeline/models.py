"""Pydantic models for human-in-the-loop override files."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, RootModel, root_validator


PatchType = Literal["force_link", "ignore", "reanchor"]


class AlignmentPatch(BaseModel):
    type: PatchType
    citation_marker: Optional[str] = None
    target_text_snippet: Optional[str] = None
    reason: Optional[str] = None

    @root_validator(skip_on_failure=True)
    def validate_fields(cls, values: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
        patch_type = values.get("type")
        citation_marker = values.get("citation_marker")
        target_text_snippet = values.get("target_text_snippet")
        reason = values.get("reason")

        if patch_type in {"force_link", "reanchor"}:
            if not citation_marker:
                raise ValueError(f"{patch_type} patches require 'citation_marker'")
            if not target_text_snippet:
                raise ValueError(f"{patch_type} patches require 'target_text_snippet'")
        if patch_type == "ignore" and not reason:
            raise ValueError("ignore patches require 'reason'")

        return values


class AlignmentOverrides(RootModel[Dict[str, List[AlignmentPatch]]]):
    root: Dict[str, List[AlignmentPatch]]

    @property
    def by_work(self) -> Dict[str, List[AlignmentPatch]]:
        return self.root

    @classmethod
    def from_path(cls, path: Path) -> "AlignmentOverrides":
        """Load and validate overrides from a YAML file."""
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)
