"""Safe RequestValidationError handling.

FastAPI's default handler for ``RequestValidationError`` serializes
``exc.errors()`` verbatim. Pydantic includes the offending raw value under the
``'input'`` key; when that value is a non-finite float (``nan``/``inf``, which
Python's ``json.loads`` accepts from ``NaN``/``Infinity`` literals),
``json.dumps(..., allow_nan=False)`` raises ``ValueError`` and the app returns
a bare 500 with no log trail instead of the correct 422.

``install_validation_handler(app)`` replaces the default handler with one that
recursively replaces non-finite floats with their string form before
serialization.
"""

from __future__ import annotations

import math
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _sanitize(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    return value


async def _request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # jsonable_encoder converts ctx['error'] exception objects to str (as
    # FastAPI's default handler does); _sanitize then strips any non-finite
    # floats that survive encoding (e.g. nan in an error's 'input' key), which
    # would otherwise crash json.dumps(allow_nan=False) with a silent 500.
    errors = _sanitize(jsonable_encoder(exc.errors()))
    return JSONResponse(status_code=422, content={"detail": errors})


def install_validation_handler(app: FastAPI) -> None:
    """Register the sanitizing 422 handler on ``app``."""
    app.add_exception_handler(RequestValidationError, _request_validation_handler)  # type: ignore[arg-type]
