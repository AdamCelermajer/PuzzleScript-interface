from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from pypdf import PdfReader


MAX_PDF_BYTES = 50 * 1024 * 1024
PAPER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")
ARXIV_PATTERN = re.compile(r"arxiv\.org/(?:abs|pdf)/([^/?#]+)", re.IGNORECASE)
READING_STATUSES = {"unread", "reading", "finished"}

DEFAULT_PAPERS = (
    {
        "id": "avo",
        "title": "AVO: Agentic Variation Operators for Autonomous Evolutionary Search",
        "authors": "Terry Chen, Zhifan Ye, Bing Xu, Zihao Ye, and collaborators · NVIDIA",
        "source_type": "arxiv",
        "source_url": "https://arxiv.org/abs/2603.24517",
        "pdf_url": "https://arxiv.org/pdf/2603.24517",
        "status": "reading",
        "page_count": 12,
        "built_in": True,
    },
    {
        "id": "vista",
        "title": "VISTA: A Visual Harness for Reasoning in an Interactive World",
        "authors": "Qiushi Han, Keya Hu, Linlu Qiu, Cathy Wu, and Kaiming He · MIT",
        "source_type": "project",
        "source_url": "https://vista-research.github.io/",
        "pdf_url": "",
        "status": "reading",
        "page_count": 0,
        "built_in": True,
    },
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str, fallback: str = "paper") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:64]
    return slug or fallback


class PaperLibrary:
    def __init__(self, root: str | Path | None = None, *, seed_defaults: bool = True) -> None:
        self.root = Path(
            root
            or Path(__file__).resolve().parents[1] / "paper_library"
        )
        self.root.mkdir(parents=True, exist_ok=True)
        if seed_defaults:
            for paper in DEFAULT_PAPERS:
                self._ensure_seed(paper)

    def _paper_dir(self, paper_id: str) -> Path:
        if not PAPER_ID_PATTERN.fullmatch(paper_id):
            raise ValueError("Invalid paper id")
        return self.root / paper_id

    @staticmethod
    def _read_json(path: Path, fallback: Any) -> Any:
        if not path.exists():
            return fallback
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return fallback

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def _ensure_seed(self, paper: dict[str, Any]) -> None:
        directory = self._paper_dir(paper["id"])
        metadata_path = directory / "paper.json"
        if metadata_path.exists():
            return
        timestamp = _now()
        record = {
            **paper,
            "created_at": timestamp,
            "updated_at": timestamp,
            "completed_at": "",
            "original_filename": "",
            "has_pdf": (directory / "paper.pdf").exists(),
        }
        self._write_json(metadata_path, record)
        self._write_json(directory / "annotations.json", [])
        self._write_json(directory / "questions.json", [])

    def _metadata(self, paper_id: str) -> dict[str, Any]:
        directory = self._paper_dir(paper_id)
        metadata = self._read_json(directory / "paper.json", None)
        if not isinstance(metadata, dict):
            raise KeyError("Paper not found")
        metadata["has_pdf"] = (directory / "paper.pdf").exists()
        annotations = self._read_json(directory / "annotations.json", [])
        questions = self._read_json(directory / "questions.json", [])
        metadata["annotation_count"] = len(annotations) if isinstance(annotations, list) else 0
        metadata["question_count"] = len(questions) if isinstance(questions, list) else 0
        return metadata

    def list_papers(self) -> list[dict[str, Any]]:
        papers = []
        for directory in self.root.iterdir():
            if not directory.is_dir() or not PAPER_ID_PATTERN.fullmatch(directory.name):
                continue
            try:
                papers.append(self._metadata(directory.name))
            except KeyError:
                continue
        papers.sort(key=lambda paper: paper.get("updated_at", ""), reverse=True)
        papers.sort(
            key=lambda paper: {"reading": 0, "unread": 1, "finished": 2}.get(
                paper.get("status"), 3
            )
        )
        return papers

    def get_paper(self, paper_id: str) -> dict[str, Any]:
        return self._metadata(paper_id)

    def update_paper(self, paper_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        directory = self._paper_dir(paper_id)
        metadata = self._metadata(paper_id)
        if "status" in changes:
            status = str(changes["status"]).strip().lower()
            if status not in READING_STATUSES:
                raise ValueError("Reading status must be unread, reading, or finished")
            metadata["status"] = status
            metadata["completed_at"] = _now() if status == "finished" else ""
        for field in ("title", "authors"):
            if field in changes:
                value = str(changes[field]).strip()
                if not value:
                    raise ValueError(f"{field} must not be blank")
                metadata[field] = value
        if "last_page" in changes:
            last_page = int(changes["last_page"])
            if last_page < 0:
                raise ValueError("last_page must not be negative")
            metadata["last_page"] = last_page
            if last_page > 0 and metadata.get("status") == "unread":
                metadata["status"] = "reading"
        metadata.pop("annotation_count", None)
        metadata.pop("question_count", None)
        metadata["updated_at"] = _now()
        self._write_json(directory / "paper.json", metadata)
        return self._metadata(paper_id)

    @staticmethod
    def _safe_remote_url(url: str) -> str:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Use a valid http or https URL")
        hostname = parsed.hostname or ""
        if hostname.lower() == "localhost":
            raise ValueError("Local URLs are not supported; upload the PDF instead")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None
        if address and (address.is_private or address.is_loopback or address.is_link_local):
            raise ValueError("Private network URLs are not supported")
        return url.strip()

    @staticmethod
    def _arxiv_details(url: str) -> tuple[str, str] | None:
        match = ARXIV_PATTERN.search(url)
        if not match:
            return None
        arxiv_id = match.group(1).removesuffix(".pdf")
        if not re.fullmatch(r"[A-Za-z0-9.\-/]+", arxiv_id):
            raise ValueError("Invalid arXiv identifier")
        return arxiv_id, f"https://arxiv.org/pdf/{arxiv_id}"

    @staticmethod
    def _download_pdf(url: str) -> bytes:
        request = Request(
            url,
            headers={"User-Agent": "PuzzleScript-World Paper Investigation/1.0"},
        )
        with urlopen(request, timeout=30) as response:
            data = response.read(MAX_PDF_BYTES + 1)
        if len(data) > MAX_PDF_BYTES:
            raise ValueError("PDF is larger than 50 MB")
        return data

    @staticmethod
    def _inspect_pdf(data: bytes) -> tuple[str, str, int, str]:
        if not data.startswith(b"%PDF-"):
            raise ValueError("The source did not return a PDF file")
        try:
            reader = PdfReader(BytesIO(data))
            metadata = reader.metadata
            title = str(getattr(metadata, "title", "") or "").strip()
            author = str(getattr(metadata, "author", "") or "").strip()
            pages = []
            for index, page in enumerate(reader.pages, start=1):
                try:
                    page_text = page.extract_text() or ""
                except Exception:
                    page_text = ""
                pages.append(f"--- Page {index} ---\n{page_text.strip()}")
            return title, author, len(reader.pages), "\n\n".join(pages).strip()
        except Exception as exc:
            raise ValueError(f"Could not read the PDF: {exc}") from exc

    def _save_pdf_record(
        self,
        *,
        paper_id: str,
        data: bytes,
        title: str,
        authors: str,
        source_type: str,
        source_url: str,
        pdf_url: str,
        original_filename: str,
    ) -> dict[str, Any]:
        pdf_title, pdf_author, page_count, text = self._inspect_pdf(data)
        directory = self._paper_dir(paper_id)
        previous = self._read_json(directory / "paper.json", {})
        timestamp = _now()
        record = {
            "id": paper_id,
            "title": title.strip() or pdf_title or Path(original_filename).stem or paper_id,
            "authors": authors.strip() or pdf_author,
            "source_type": source_type,
            "source_url": source_url,
            "pdf_url": pdf_url,
            "status": previous.get("status", "unread"),
            "page_count": page_count,
            "last_page": previous.get("last_page", 0),
            "built_in": previous.get("built_in", False),
            "created_at": previous.get("created_at", timestamp),
            "updated_at": timestamp,
            "completed_at": previous.get("completed_at", ""),
            "original_filename": original_filename,
            "has_pdf": True,
        }
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "paper.pdf").write_bytes(data)
        (directory / "text.txt").write_text(text + "\n", encoding="utf-8")
        self._write_json(directory / "paper.json", record)
        if not (directory / "annotations.json").exists():
            self._write_json(directory / "annotations.json", [])
        if not (directory / "questions.json").exists():
            self._write_json(directory / "questions.json", [])
        return self._metadata(paper_id)

    def import_url(self, url: str, *, title: str = "", authors: str = "") -> dict[str, Any]:
        source_url = self._safe_remote_url(url)
        arxiv = self._arxiv_details(source_url)
        if arxiv:
            arxiv_id, pdf_url = arxiv
            paper_id = "avo" if arxiv_id == "2603.24517" else f"arxiv-{arxiv_id.replace('.', '-').replace('/', '-').lower()}"
            source_type = "arxiv"
            original_filename = f"{arxiv_id.replace('/', '-')}.pdf"
        else:
            pdf_url = source_url
            source_type = "pdf_url"
            original_filename = Path(urlparse(source_url).path).name or "paper.pdf"
            digest = hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:8]
            paper_id = f"{_slug(title or Path(original_filename).stem)}-{digest}"
        data = self._download_pdf(pdf_url)
        return self._save_pdf_record(
            paper_id=paper_id,
            data=data,
            title=title,
            authors=authors,
            source_type=source_type,
            source_url=source_url,
            pdf_url=pdf_url,
            original_filename=original_filename,
        )

    def upload_pdf(
        self,
        data: bytes,
        *,
        filename: str,
        title: str = "",
        authors: str = "",
    ) -> dict[str, Any]:
        if len(data) > MAX_PDF_BYTES:
            raise ValueError("PDF is larger than 50 MB")
        safe_filename = Path(filename or "paper.pdf").name
        digest = hashlib.sha256(data).hexdigest()[:8]
        paper_id = f"{_slug(title or Path(safe_filename).stem)}-{digest}"
        return self._save_pdf_record(
            paper_id=paper_id,
            data=data,
            title=title,
            authors=authors,
            source_type="upload",
            source_url="",
            pdf_url="",
            original_filename=safe_filename,
        )

    def pdf_path(self, paper_id: str) -> Path:
        self._metadata(paper_id)
        path = self._paper_dir(paper_id) / "paper.pdf"
        if not path.is_file():
            raise KeyError("Paper PDF not found")
        return path

    def annotations(self, paper_id: str) -> list[dict[str, Any]]:
        self._metadata(paper_id)
        items = self._read_json(self._paper_dir(paper_id) / "annotations.json", [])
        return items if isinstance(items, list) else []

    def add_annotation(self, paper_id: str, annotation: dict[str, Any]) -> dict[str, Any]:
        items = self.annotations(paper_id)
        requested_id = annotation.get("id")
        existing = next(
            (item for item in items if requested_id and item.get("id") == requested_id),
            None,
        )
        if existing is not None:
            return existing
        record = {
            **annotation,
            "id": annotation.get("id") or uuid4().hex,
            "paper_id": paper_id,
            "comment": str(annotation.get("comment", "")),
            "created_at": annotation.get("created_at") or _now(),
            "updated_at": _now(),
        }
        items.insert(0, record)
        self._write_json(self._paper_dir(paper_id) / "annotations.json", items)
        self._touch(paper_id)
        return record

    def update_annotation(
        self, paper_id: str, annotation_id: str, changes: dict[str, Any]
    ) -> dict[str, Any]:
        items = self.annotations(paper_id)
        record = next((item for item in items if item.get("id") == annotation_id), None)
        if record is None:
            raise KeyError("Underline not found")
        if "comment" in changes:
            record["comment"] = str(changes["comment"])
        record["updated_at"] = _now()
        self._write_json(self._paper_dir(paper_id) / "annotations.json", items)
        self._touch(paper_id)
        return record

    def delete_annotation(self, paper_id: str, annotation_id: str) -> None:
        items = self.annotations(paper_id)
        kept = [item for item in items if item.get("id") != annotation_id]
        if len(kept) == len(items):
            raise KeyError("Underline not found")
        self._write_json(self._paper_dir(paper_id) / "annotations.json", kept)
        self._touch(paper_id)

    def questions(self, paper_id: str) -> list[dict[str, Any]]:
        self._metadata(paper_id)
        items = self._read_json(self._paper_dir(paper_id) / "questions.json", [])
        return items if isinstance(items, list) else []

    def save_question(self, paper_ids: list[str], question: dict[str, Any]) -> dict[str, Any]:
        record = {
            **question,
            "id": question.get("id") or uuid4().hex,
            "paper_ids": paper_ids,
            "created_at": question.get("created_at") or _now(),
        }
        for paper_id in paper_ids:
            items = self.questions(paper_id)
            if not any(item.get("id") == record["id"] for item in items):
                items.insert(0, record)
            self._write_json(self._paper_dir(paper_id) / "questions.json", items)
            self._touch(paper_id)
        return record

    def context(self, paper_ids: list[str], annotation_ids: list[str]) -> str:
        sections = []
        per_paper_budget = max(8_000, 60_000 // max(1, len(paper_ids)))
        linked_ids = set(annotation_ids)
        for paper_id in paper_ids:
            paper = self._metadata(paper_id)
            header = (
                f"PAPER {paper_id}: {paper.get('title', '')}\n"
                f"Authors: {paper.get('authors', '')}\n"
                f"Source: {paper.get('source_url') or paper.get('pdf_url') or 'uploaded PDF'}"
            )
            linked = [
                item for item in self.annotations(paper_id)
                if item.get("id") in linked_ids
            ]
            underline_text = "\n".join(
                f"- Page {item.get('page') or '?'}: {item.get('quote', '')}"
                + (f"\n  Comment: {item.get('comment')}" if item.get("comment") else "")
                for item in linked
            )
            text_path = self._paper_dir(paper_id) / "text.txt"
            source_text = text_path.read_text(encoding="utf-8") if text_path.exists() else ""
            section = header
            if underline_text:
                section += f"\nLinked underlines:\n{underline_text}"
            if source_text:
                excerpt = source_text[:per_paper_budget]
                section += f"\nExtracted paper text:\n{excerpt}"
            sections.append(section)
        return "\n\n".join(sections)

    def _touch(self, paper_id: str) -> None:
        directory = self._paper_dir(paper_id)
        metadata = self._metadata(paper_id)
        metadata.pop("annotation_count", None)
        metadata.pop("question_count", None)
        metadata["updated_at"] = _now()
        self._write_json(directory / "paper.json", metadata)
