from __future__ import annotations

import re

_LINK_RE = re.compile(r"!?\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_BOLD_ITALIC_RE = re.compile(r"(\*\*\*|___)(.*?)\1", re.DOTALL)
_BOLD_RE = re.compile(r"(\*\*|__)(.*?)\1", re.DOTALL)
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.*?)\*(?!\*)|(?<!_)_(?!_)(.*?)_(?!_)", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]*)`")
_CODE_BLOCK_RE = re.compile(r"```[a-zA-Z0-9_-]*\n?(.*?)```", re.DOTALL)
_BLOCKQUOTE_RE = re.compile(r"^\s*>\s?", re.MULTILINE)
_ORDERED_LIST_RE = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)
_UNORDERED_LIST_RE = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_RULE_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$", re.MULTILINE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _replace_link(match: re.Match[str]) -> str:
    label = (match.group(1) or "").strip()
    url = (match.group(2) or "").strip()
    if not label:
        return url
    if label == url:
        return url
    return f"{label}: {url}"


def markdown_to_linkedin_text(value: str, max_length: int = 3000) -> str:
    """Convert Markdown-ish generated copy into LinkedIn-friendly plain text.

    LinkedIn feed posts are plain text. This keeps the useful structure while
    removing markdown-only syntax that LinkedIn will not render.
    """
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""

    text = _CODE_BLOCK_RE.sub(lambda m: m.group(1).strip(), text)
    text = _LINK_RE.sub(_replace_link, text)
    text = _HEADING_RE.sub("", text)
    text = _BLOCKQUOTE_RE.sub("", text)
    text = _RULE_RE.sub("", text)
    text = _ORDERED_LIST_RE.sub("â€¢ ", text)
    text = _UNORDERED_LIST_RE.sub("â€¢ ", text)
    text = _BOLD_ITALIC_RE.sub(lambda m: m.group(2), text)
    text = _BOLD_RE.sub(lambda m: m.group(2), text)
    text = _ITALIC_RE.sub(lambda m: m.group(1) or m.group(2) or "", text)
    text = _INLINE_CODE_RE.sub(lambda m: m.group(1), text)
    text = _HTML_TAG_RE.sub("", text)

    # Drop simple markdown table separator rows and trim table pipes.
    cleaned_lines: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            cleaned_lines.append("")
            continue
        if re.fullmatch(r"\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?", line):
            continue
        if "|" in line:
            parts = [part.strip() for part in line.strip("|").split("|") if part.strip()]
            if len(parts) > 1:
                line = " â€” ".join(parts)
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    if len(text) > max_length:
        text = text[: max_length - 1].rstrip() + "â€¦"
    return text
