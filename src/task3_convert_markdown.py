"""
Task 3 — Convert toàn bộ file trong data/landing/ thành Markdown.

Sử dụng MarkItDown của Microsoft để convert PDF/DOCX → Markdown.
JSON articles từ task2 được extract content_markdown trực tiếp.

Output: data/standardized/legal/ và data/standardized/news/
"""

import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

LANDING_DIR = Path(__file__).parent.parent / "data" / "landing"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "standardized"


def convert_legal_docs() -> int:
    """Convert PDF/DOCX files trong data/landing/legal/ sang markdown."""
    from markitdown import MarkItDown

    legal_dir = LANDING_DIR / "legal"
    output_dir = OUTPUT_DIR / "legal"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not legal_dir.exists():
        log.warning(f"  ✗ Legal dir not found: {legal_dir}")
        return 0

    md = MarkItDown()
    count = 0

    for filepath in legal_dir.iterdir():
        if filepath.suffix.lower() not in (".pdf", ".docx", ".doc"):
            continue

        output_path = output_dir / f"{filepath.stem}.md"
        if output_path.exists():
            log.info(f"  ✓ Already converted: {filepath.name}")
            count += 1
            continue

        log.info(f"  Converting: {filepath.name}")
        try:
            result = md.convert(str(filepath))
            content = result.text_content
            if not content or len(content) < 100:
                log.warning(f"    ✗ Very short output ({len(content)} chars), skipping")
                continue
            output_path.write_text(content, encoding="utf-8")
            log.info(f"    ✓ Saved: {output_path.name} ({len(content):,} chars)")
            count += 1
        except Exception as e:
            log.error(f"    ✗ Failed to convert {filepath.name}: {e}")

    return count


def convert_news_articles() -> int:
    """Convert JSON crawled articles trong data/landing/news/ sang markdown."""
    news_dir = LANDING_DIR / "news"
    output_dir = OUTPUT_DIR / "news"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not news_dir.exists():
        log.warning(f"  ✗ News dir not found: {news_dir}")
        return 0

    count = 0

    for filepath in news_dir.iterdir():
        if filepath.suffix.lower() != ".json":
            continue

        output_path = output_dir / f"{filepath.stem}.md"
        if output_path.exists():
            log.info(f"  ✓ Already converted: {filepath.name}")
            count += 1
            continue

        log.info(f"  Converting: {filepath.name}")
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))

            # Build markdown with metadata header
            title = data.get("title", "Unknown Title")
            url = data.get("url", "N/A")
            date_crawled = data.get("date_crawled", "N/A")
            content = data.get("content_markdown", "")

            header = f"# {title}\n\n"
            header += f"**Source:** {url}\n"
            header += f"**Crawled:** {date_crawled}\n\n---\n\n"

            full_content = header + content
            output_path.write_text(full_content, encoding="utf-8")
            log.info(f"    ✓ Saved: {output_path.name} ({len(full_content):,} chars)")
            count += 1
        except Exception as e:
            log.error(f"    ✗ Failed to convert {filepath.name}: {e}")

    return count


def convert_all() -> None:
    """Convert toàn bộ files từ data/landing/ sang data/standardized/."""
    log.info("=== Task 3: Convert to Markdown (MarkItDown) ===")

    log.info("\n--- Legal Documents ---")
    legal_count = convert_legal_docs()

    log.info("\n--- News Articles ---")
    news_count = convert_news_articles()

    # Summary
    total_md = list(OUTPUT_DIR.rglob("*.md"))
    log.info(f"\n✓ Done! Converted {legal_count} legal + {news_count} news = {len(total_md)} total .md files")
    log.info(f"  Output dir: {OUTPUT_DIR}")


if __name__ == "__main__":
    convert_all()
