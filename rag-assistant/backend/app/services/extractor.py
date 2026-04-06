"""
Text extraction from uploaded files.
Supports: PDF (via PyMuPDF), TXT, Markdown.
Returns plain text string for downstream chunking.
"""

from pathlib import Path
import markdown


def extract_text(file_path: Path, file_type: str) -> str:
    """
    Extract raw text from an uploaded file.

    Args:
        file_path: Absolute or relative path to the saved file.
        file_type:  "pdf" | "txt" | "md"

    Returns:
        A single string of all extracted text.

    Raises:
        ValueError: If file_type is unsupported.
        RuntimeError: If extraction fails.
    """
    if file_type == "pdf":
        return _extract_pdf(file_path)
    elif file_type == "txt":
        return _extract_txt(file_path)
    elif file_type == "md":
        return _extract_markdown(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")


def _extract_pdf(path: Path) -> str:
    """Use PyMuPDF (fitz) to extract text page by page."""
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(str(path))
        pages = []
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text("text")
            if text.strip():
                # Prefix each page so chunks can reference page numbers later
                pages.append(f"[Page {page_num}]\n{text.strip()}")
        doc.close()
        return "\n\n".join(pages)
    except Exception as e:
        raise RuntimeError(f"PDF extraction failed for {path.name}: {e}") from e


def _extract_txt(path: Path) -> str:
    """Read plain text, trying UTF-8 then falling back to latin-1."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def _extract_markdown(path: Path) -> str:
    """
    Convert Markdown to plain text.
    We render to HTML first, then strip tags so structure
    (headings, lists) becomes readable plain text.
    """
    raw = path.read_text(encoding="utf-8")
    # Convert to HTML, then strip tags for plain text
    html = markdown.markdown(raw)
    return _strip_html_tags(html)


def _strip_html_tags(html: str) -> str:
    """Minimal HTML tag stripper — no external deps needed."""
    import re
    # Replace block-level closing tags with newlines
    html = re.sub(r"</(?:p|h[1-6]|li|ul|ol|blockquote|pre|div)>", "\n", html, flags=re.IGNORECASE)
    # Strip all remaining tags
    html = re.sub(r"<[^>]+>", "", html)
    # Collapse excessive blank lines
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()
