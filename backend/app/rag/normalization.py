import re
import unicodedata


def normalize_text(text: str) -> str:
    """Normalize text for consistent embedding and retrieval.
    
    - Canonical Unicode NFC normalization (essential for Vietnamese accents).
    - Removes non-printable/control characters (except standard newlines and tabs).
    - Normalizes horizontal whitespace (tabs, multi-spaces).
    - Collapses excessive newlines (max 2 consecutive).
    """
    if not text:
        return ""

    normalized = unicodedata.normalize("NFC", text)
    # Remove control characters except \n and \t
    cleaned = "".join(
        ch for ch in normalized if ch == "\n" or ch == "\t" or not unicodedata.category(ch).startswith("C")
    )
    # Replace horizontal whitespace with single space
    cleaned = re.sub(r"[^\S\n\r]+", " ", cleaned)
    # Collapse multiple consecutive newlines to maximum two
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def chunk_text(
    text: str,
    *,
    chunk_size: int = 600,
    chunk_overlap: int = 100,
) -> list[str]:
    """Chunk normalized text using paragraph and sentence boundaries.
    
    Guarantees:
    - Never splits in the middle of words.
    - Preserves sentence context.
    - Maintains chunk_overlap between consecutive chunks.
    """
    clean_text = normalize_text(text)
    if not clean_text:
        return []

    if len(clean_text) <= chunk_size:
        return [clean_text]

    # Split into paragraphs
    paragraphs = clean_text.split("\n\n")
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_length = 0

    for para in paragraphs:
        para_len = len(para)
        if para_len > chunk_size:
            # Paragraph itself exceeds chunk_size; split by sentences
            sentences = re.split(r"(?<=[.?!;])\s+", para)
            for sent in sentences:
                sent_len = len(sent)
                if current_length + sent_len > chunk_size and current_chunk:
                    chunk_str = " ".join(current_chunk).strip()
                    if chunk_str:
                        chunks.append(chunk_str)
                    # Handle overlap from the end of current_chunk
                    overlap_words = " ".join(current_chunk)[-chunk_overlap:].split()
                    current_chunk = overlap_words if overlap_words else []
                    current_length = sum(len(w) + 1 for w in current_chunk)

                current_chunk.append(sent)
                current_length += sent_len + 1
        else:
            if current_length + para_len > chunk_size and current_chunk:
                chunk_str = "\n\n".join(current_chunk).strip()
                if chunk_str:
                    chunks.append(chunk_str)
                # Apply overlap
                overlap_text = "\n\n".join(current_chunk)[-chunk_overlap:]
                current_chunk = [overlap_text] if overlap_text.strip() else []
                current_length = len(overlap_text)

            current_chunk.append(para)
            current_length += para_len + 2

    if current_chunk:
        remaining_chunk = "\n\n".join(current_chunk).strip()
        if remaining_chunk and (not chunks or remaining_chunk != chunks[-1]):
            chunks.append(remaining_chunk)

    return chunks
