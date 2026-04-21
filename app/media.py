from __future__ import annotations


def image_public_url(public_base_url: str | None, filename: str | None) -> str | None:
    if not public_base_url or not filename:
        return None
    base = public_base_url.rstrip("/")
    return f"{base}/static/images/{filename}"
