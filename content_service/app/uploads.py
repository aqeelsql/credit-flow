from pathlib import Path
from uuid import uuid4

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.config import Settings
from app.errors import ContentError

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}


def save_upload(settings: Settings, file: FileStorage | None, account_id: str) -> str:
    if not file or not file.filename:
        raise ContentError("missing_file", "Image file is required.", 422)
    filename = secure_filename(file.filename)
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise ContentError("unsupported_file_type", "Only png, jpg, jpeg, webp, and gif uploads are allowed.", 422)
    root = Path(settings.upload_dir).resolve()
    account_dir = (root / account_id).resolve()
    if not str(account_dir).startswith(str(root)):
        raise ContentError("invalid_upload_path", "Upload path is invalid.", 500)
    account_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4()}.{extension}"
    file.save(account_dir / stored_name)
    return f"local://content/{account_id}/{stored_name}"
