"""
metadata_store.py — persist and load per-document metadata.

Each uploaded document gets a JSON sidecar: <basename>.meta.json stored in
UPLOAD_DIR alongside the .txt file. Bundled KB documents receive in-memory
defaults with no file needed.
"""
import json
import os
from datetime import datetime, timezone


BUNDLED_DEFAULTS: dict[str, dict] = {
    "loans.txt":            {"document_type": "reference", "loan_type": "general",  "version": "1.0", "effective_date": None},
    "loan_types.txt":       {"document_type": "reference", "loan_type": "general",  "version": "1.0", "effective_date": None},
    "loan_interest.txt":    {"document_type": "reference", "loan_type": "general",  "version": "1.0", "effective_date": None},
    "loan_repayment.txt":   {"document_type": "reference", "loan_type": "general",  "version": "1.0", "effective_date": None},
    "loan_eligibility.txt": {"document_type": "reference", "loan_type": "general",  "version": "1.0", "effective_date": None},
    "loan_risks.txt":       {"document_type": "reference", "loan_type": "general",  "version": "1.0", "effective_date": None},
}


def _meta_path(upload_dir: str, filename: str) -> str:
    base = os.path.splitext(filename)[0]
    return os.path.join(upload_dir, f"{base}.meta.json")


def load_metadata(upload_dir: str, filename: str) -> dict:
    """Return metadata dict for a document. Falls back to defaults."""
    if filename in BUNDLED_DEFAULTS:
        m = dict(BUNDLED_DEFAULTS[filename])
        m.update({"filename": filename, "uploaded": False, "upload_date": None})
        return m

    path = _meta_path(upload_dir, filename)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            pass

    # Uploaded doc without a sidecar — sensible defaults
    return {
        "filename": filename,
        "document_type": "general",
        "loan_type": "general",
        "version": "1.0",
        "effective_date": None,
        "upload_date": None,
        "uploaded": True,
    }


def save_metadata(upload_dir: str, filename: str, data: dict) -> None:
    path = _meta_path(upload_dir, filename)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def delete_metadata(upload_dir: str, filename: str) -> None:
    path = _meta_path(upload_dir, filename)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def make_upload_metadata(
    filename: str,
    document_type: str | None,
    loan_type: str | None,
    version: str | None,
    effective_date: str | None,
) -> dict:
    return {
        "filename": filename,
        "document_type": (document_type or "general").strip() or "general",
        "loan_type": (loan_type or "general").strip() or "general",
        "version": (version or "1.0").strip() or "1.0",
        "effective_date": (effective_date or "").strip() or None,
        "upload_date": datetime.now(timezone.utc).isoformat(),
        "uploaded": True,
    }
