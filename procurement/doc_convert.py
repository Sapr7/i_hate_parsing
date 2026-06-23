# -*- coding: utf-8 -*-
"""Convert legacy .doc (OLE) to .docx for table parsing."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

OLE_MAGIC = b"\xd0\xcf\x11\xe0"


def is_ole_doc(raw: bytes, title: str = "", url: str = "") -> bool:
    if len(raw) < 4 or raw[:4] != OLE_MAGIC:
        return False
    hint = f"{title} {url}".lower()
    if any(x in hint for x in (".xls", ".xlsx")):
        if ".doc" not in hint or ".docx" in hint:
            return False
    if ".docx" in hint:
        return False
    if ".doc" in hint:
        return True
    # OLE without extension: assume Word if not Excel hint.
    if "xls" in hint and "doc" not in hint:
        return False
    return True


def _word_com_convert(doc_path: str, docx_path: str) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import win32com.client  # type: ignore
    except ImportError:
        return False
    word = None
    doc = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(os.path.abspath(doc_path), ReadOnly=True)
        doc.SaveAs2(os.path.abspath(docx_path), FileFormat=16)
        doc.Close(False)
        return Path(docx_path).is_file() and Path(docx_path).stat().st_size > 0
    except Exception:
        return False
    finally:
        if doc is not None:
            try:
                doc.Close(False)
            except Exception:
                pass
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass


def _libreoffice_convert(doc_path: str, out_dir: str) -> Optional[str]:
    candidates = [
        shutil.which("soffice"),
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    soffice = next((p for p in candidates if p and Path(p).is_file()), None)
    if not soffice:
        return None
    try:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "docx", "--outdir", out_dir, doc_path],
            check=True,
            timeout=120,
            capture_output=True,
        )
    except Exception:
        return None
    docx = Path(out_dir) / (Path(doc_path).stem + ".docx")
    return str(docx) if docx.is_file() else None


def convert_doc_to_docx(raw: bytes, title: str = "document.doc") -> Optional[bytes]:
    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in title)
    if not safe_name.lower().endswith(".doc"):
        safe_name += ".doc"
    with tempfile.TemporaryDirectory() as td:
        doc_path = os.path.join(td, safe_name)
        docx_path = os.path.join(td, Path(safe_name).stem + ".docx")
        Path(doc_path).write_bytes(raw)

        if _word_com_convert(doc_path, docx_path):
            return Path(docx_path).read_bytes()

        alt = _libreoffice_convert(doc_path, td)
        if alt:
            return Path(alt).read_bytes()
    return None
