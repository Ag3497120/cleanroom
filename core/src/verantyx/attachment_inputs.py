"""Explicit, bounded PDF/image inputs. Never grant access to a parent folder."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from threading import RLock
import base64
import hashlib
import math
import os
import re
import shlex
import stat
import uuid

from .errors import LedgerError

EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif")
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_IMAGE_BYTES = 6 * 1024 * 1024
MAX_PAGES = 12
MAX_TEXT_BYTES = 120000
PDF_LOCK = RLock()


def require(condition, reason):
    if not condition:
        raise LedgerError("ATTACHMENT_INPUT", {"reason": reason})


def parse_argument(argument):
    """A quoted file path with optional explicit page range or text-only mode."""
    try:
        tokens = shlex.split(argument, posix=os.name != "nt")
    except ValueError:
        raise LedgerError("ATTACHMENT_INPUT", {"reason": "QUOTE_PATH"}) from None
    text_only, pages, paths = False, None, []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--text":
            text_only = True
        elif token == "--pages":
            index += 1
            require(index < len(tokens), "PAGE_RANGE")
            selected = set()
            for part in tokens[index].split(","):
                require(re.fullmatch(r"[1-9][0-9]*(?:-[1-9][0-9]*)?", part), "PAGE_RANGE")
                edges = [int(n) for n in part.split("-")]
                start, end = edges[0], edges[-1]
                require(1 <= start <= end <= 10000 and end - start < MAX_PAGES, "PAGE_RANGE")
                selected.update(range(start, end + 1))
            require(0 < len(selected) <= MAX_PAGES, "PAGE_LIMIT")
            pages = sorted(selected)
        else:
            paths.append(token.strip('"'))
        index += 1
    require(len(paths) == 1, "ONE_QUOTED_PATH")
    require(Path(paths[0]).suffix.lower() in EXTENSIONS, "PDF_OR_IMAGE_REQUIRED")
    require(not text_only or Path(paths[0]).suffix.lower() == ".pdf", "TEXT_ONLY_PDF")
    return {"path": paths[0], "text_only": text_only, "pages": pages}


def paths_in_text(text):
    """Recognize literal attachment paths, not the meaning of a task."""
    pattern = re.compile(
        r"""(?P<quoted>["'])(?P<qpath>(?:/|~/|[A-Za-z]:[\\/]).*?\.(?:pdf|png|jpe?g|webp|gif))(?P=quoted)|(?P<path>(?:/|~/|[A-Za-z]:[\\/])(?:\\ |[^\s"'<>])+?\.(?:pdf|png|jpe?g|webp|gif))(?=$|[\s"'、。。，）)\]])""",
        re.IGNORECASE)
    # A URL's final scheme letter (e.g. the s in https://) must not
    # be mistaken for a Windows drive. Exclude entire URI spans first.
    remote_spans = [match.span() for match in re.finditer(
        r"""[A-Za-z][A-Za-z0-9+.-]*://[^\s"'<>]+""", text)]
    results = []
    for match in pattern.finditer(text):
        if any(start < match.end() and match.start() < end
               for start, end in remote_spans):
            continue
        path = (match.group("qpath") or match.group("path")).replace("\\ ", " ")
        results.append({"path": path, "text_only": False, "pages": None})
    return results


def selections(text, queued=()):
    result, seen = [], set()
    for item in [*queued, *paths_in_text(text)]:
        key = str(Path(item["path"]).expanduser())
        if key not in seen:
            result.append(dict(item))
            seen.add(key)
    require(len(result) <= 4, "FILE_COUNT_LIMIT")
    return result


def _read_regular(path, maximum=MAX_FILE_BYTES):
    path = Path(path).expanduser().absolute()
    require(not path.is_symlink(), "SYMLINK")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode), "REGULAR_FILE_REQUIRED")
        require(0 < info.st_size <= maximum, "FILE_SIZE_LIMIT")
        raw = stream.read(maximum + 1)
    require(0 < len(raw) <= maximum, "FILE_SIZE_LIMIT")
    return raw


def _write(path, raw):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)


def _image(image, directory, index):
    from PIL import Image, ImageOps
    require(0 < image.width * image.height <= 40_000_000, "IMAGE_PIXEL_LIMIT")
    image = ImageOps.exif_transpose(image)
    image.thumbnail((1600, 1600))
    if image.mode in ("RGBA", "LA") or "transparency" in image.info:
        rgba = image.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, "white")
        canvas.paste(rgba, mask=rgba.getchannel("A"))
    else:
        canvas = image.convert("RGB")
    data = BytesIO()
    canvas.save(data, format="JPEG", quality=88, optimize=True)
    raw = data.getvalue()
    path = directory / (str(index) + ".jpg")
    _write(path, raw)
    return {"staged_path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
            "mime_type": "image/jpeg", "bytes": len(raw), "width": canvas.width, "height": canvas.height}


def prepare(root, selected):
    """Called only after explicit send approval. Copies are local provenance."""
    if not selected:
        return []
    require(len(selected) <= 4, "FILE_COUNT_LIMIT")
    from PIL import Image
    base = Path(root).resolve() / ".verantyx" / "attachment-inputs"
    require(not base.is_symlink() and not base.parent.is_symlink(), "UNSAFE_STORE")
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    result, total_images, total_bytes, total_text = [], 0, 0, 0
    for item in selected:
        source = Path(item["path"]).expanduser()
        source = source if source.is_absolute() else Path(root) / source
        extension = source.suffix.lower()
        require(extension in EXTENSIONS, "PDF_OR_IMAGE_REQUIRED")
        raw = _read_regular(source)
        sha = hashlib.sha256(raw).hexdigest()
        directory = base / (sha + "-" + uuid.uuid4().hex[:12])
        directory.mkdir(mode=0o700)
        _write(directory / ("original" + extension), raw)
        record = {"id": "attachment-" + sha, "name": source.name, "sha256": sha,
                  "bytes": len(raw), "pages": [], "text_only": bool(item.get("text_only")),
                  "original_path": str(source.absolute()), "untrusted_source": True}
        if extension == ".pdf":
            import pypdfium2 as pdfium
            with PDF_LOCK:
                try:
                    with pdfium.PdfDocument(raw) as pdf:
                        numbers = item.get("pages") or list(range(1, len(pdf) + 1))
                        require(0 < len(numbers) <= MAX_PAGES, "PAGE_LIMIT_USE_PAGES")
                        require(all(type(n) is int and 1 <= n <= len(pdf) for n in numbers), "PAGE_RANGE")
                        record["total_pages"] = len(pdf)
                        for number in numbers:
                            page = pdf[number - 1]
                            try:
                                textpage = page.get_textpage()
                                try:
                                    text = textpage.get_text_bounded()
                                finally:
                                    textpage.close()
                                total_text += len(text.encode("utf-8"))
                                require(total_text <= MAX_TEXT_BYTES, "TEXT_LIMIT_USE_PAGES")
                                entry = {"number": number, "text": text}
                                if not record["text_only"]:
                                    width, height = page.get_size()
                                    require(math.isfinite(width) and math.isfinite(height)
                                            and width > 0 and height > 0, "PAGE_DIMENSIONS")
                                    bitmap = page.render(scale=min(2, 1600 / max(width, height)))
                                    try:
                                        entry["image"] = _image(bitmap.to_pil(), directory, number)
                                    finally:
                                        bitmap.close()
                                record["pages"].append(entry)
                            finally:
                                page.close()
                except pdfium.PdfiumError:
                    raise LedgerError("ATTACHMENT_INPUT", {"reason": "PDF_UNREADABLE_OR_ENCRYPTED"}) from None
            if record["text_only"]:
                require(any(p["text"].strip() for p in record["pages"]), "NO_PDF_TEXT_USE_VISION")
        else:
            require(not record["text_only"] and not item.get("pages"), "IMAGE_OPTIONS")
            with Image.open(BytesIO(raw)) as image:
                require(getattr(image, "n_frames", 1) == 1, "ANIMATED_IMAGE_SELECT_FRAME")
                record["pages"].append({"number": 1, "text": "", "image": _image(image, directory, 1)})
        for page in record["pages"]:
            if "image" in page:
                total_images += 1
                total_bytes += page["image"]["bytes"]
        require(total_images <= MAX_PAGES and total_bytes <= MAX_IMAGE_BYTES, "IMAGE_BATCH_LIMIT")
        result.append(record)
    return result


def image_inputs(request):
    """Verify host-selected files again before encoding them for a provider."""
    result, total = [], 0
    for record in request.get("attachments", []):
        for page in record.get("pages", []):
            image = page.get("image")
            if not image:
                continue
            path = Path(image["staged_path"])
            require(path.is_absolute() and path.resolve() == path
                    and path.parent.parent.name == "attachment-inputs"
                    and path.parent.parent.parent.name == ".verantyx", "MEDIA_SCOPE")
            raw = _read_regular(path, MAX_IMAGE_BYTES)
            require(hashlib.sha256(raw).hexdigest() == image["sha256"]
                    and image["mime_type"] == "image/jpeg", "MEDIA_CHANGED")
            total += len(raw)
            require(total <= MAX_IMAGE_BYTES and len(result) < MAX_PAGES, "IMAGE_BATCH_LIMIT")
            result.append({**image, "data": base64.b64encode(raw).decode("ascii"),
                           "label": record["name"] + " / page " + str(page["number"])})
    return result


def public_request(request):
    """Keep local paths in the ledger, not in the model's text envelope."""
    def clean(value):
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items()
                    if key not in ("staged_path", "original_path")}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value
    return clean(deepcopy(request))
