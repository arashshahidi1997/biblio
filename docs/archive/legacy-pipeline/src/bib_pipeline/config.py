"""Pipeline configuration for extraction tools."""

from __future__ import annotations

from pydantic import BaseModel


class DoclingConfig(BaseModel):
    version: str = "1.0.0"
    do_ocr: bool = False
    do_table_structure: bool = True


class GrobidConfig(BaseModel):
    version: str = "0.8.0"
    service_url: str = "http://localhost:8070"
    batch_size: int = 10
    consolidate_header: str = "1"
    consolidate_citations: str = "1"


class PipelineConfig(BaseModel):
    pipeline_mode: str = "docling_only"
    docling: DoclingConfig = DoclingConfig()
    grobid: GrobidConfig = GrobidConfig()


config = PipelineConfig()
