from __future__ import annotations

from pathlib import Path

from docx import Document

from .extractor import collect_document_paragraphs, set_paragraph_text
from .models import AnonymizedDocument
from .replacer import ReplacementEngine
from .utils import dump_json, ensure_directory, get_logger, repair_pdf_artifacts

logger = get_logger(__name__)


class DocxExporter:
    def export(
        self,
        document: AnonymizedDocument,
        output_path: str | Path,
        source_path: str | Path | None = None,
        engine: ReplacementEngine | None = None,
    ) -> Path:
        path = Path(output_path)
        ensure_directory(path.parent)
        source = Path(source_path or document.source_path)
        doc = Document(source)

        paragraphs = collect_document_paragraphs(doc)
        if len(paragraphs) != len(document.pages):
            raise RuntimeError(
                f"DOCX walk mismatch: extracted {len(document.pages)} blocks, "
                f"writer saw {len(paragraphs)}. Refusing to scramble the file."
            )

        replacer = engine or ReplacementEngine()
        replacer.mapping = document.replacements

        for paragraph, block in zip(paragraphs, document.pages, strict=False):
            current = repair_pdf_artifacts(paragraph.text)
            updated = replacer.replace_text(current)
            if updated != paragraph.text:
                set_paragraph_text(paragraph, updated)

        doc.save(path)
        logger.info("Wrote structured DOCX: %s", path)
        return path

    def export_mapping(self, document: AnonymizedDocument, output_path: str | Path) -> Path:
        path = Path(output_path)
        payload = {
            item.original: {
                "fake": item.fake,
                "entity_type": item.entity_type.value,
            }
            for item in document.replacements.items()
        }
        dump_json(path, payload)
        logger.info("Wrote replacement mapping: %s", path)
        return path

    def export_entities(self, document: AnonymizedDocument, output_path: str | Path) -> Path:
        path = Path(output_path)
        payload = [
            {
                "text": entity.text,
                "entity_type": entity.entity_type.value,
                "block_index": entity.page_number,
                "start": entity.start,
                "end": entity.end,
                "score": entity.score,
                "detector": entity.detector.value,
            }
            for entity in document.entities
        ]
        dump_json(path, payload)
        logger.info("Wrote %s detected entities: %s", len(payload), path)
        return path
