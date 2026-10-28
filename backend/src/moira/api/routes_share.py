"""The Android share target (§4.3.12): the installed web app receives a share and saves it.

Browsers cannot add the X-Moira header to a share-target POST, so this route checks the
Origin instead; the session cookie is SameSite=Lax, so a cross-site form never carries it.
"""

from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse

from moira.api.deps import ServicesDep, UserDep, rate
from moira.api.uploads import read_uploads
from moira.capture.service import CaptureInput
from moira.errors import Forbidden, ValidationFailed

router = APIRouter()


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


@router.post("/share", dependencies=[Depends(rate("share", 10, 60))])
async def share(
    request: Request,
    user: UserDep,
    services: ServicesDep,
    title: str = Form(default="", max_length=1_000),
    text: str = Form(default="", max_length=10_000),
    url: str = Form(default="", max_length=4_000),
    files: list[UploadFile] = File(default=[]),  # noqa: B008
) -> RedirectResponse:
    origin = request.headers.get("origin")
    if origin is not None and origin != _origin(services.settings.public_base_url):
        raise Forbidden("Shares must come from the installed app.")
    body = "\n".join(p for p in (title.strip(), text.strip(), url.strip()) if p)
    # Android puts the link in text as often as in url; avoid saying it twice.
    if url.strip() and text.count(url.strip()):
        body = "\n".join(p for p in (title.strip(), text.strip()) if p)
    media = await read_uploads(services.tmp_dir, files, None)
    if media.kind == "text" and not body:
        raise ValidationFailed("Nothing to save.")
    r = services.capture.capture(
        CaptureInput(
            channel="web", kind=media.kind, text=body, tmp_files=media.paths, media_meta=media.meta
        ),
        user,
    )
    assert r.nugget is not None
    return RedirectResponse(f"/?saved={r.nugget.public_id}", status_code=303)
