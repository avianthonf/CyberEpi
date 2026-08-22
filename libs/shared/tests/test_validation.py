"""Contract tests for shared.validation install_validation_handler.

Defends the observable contract: pydantic ValidationErrors whose raw input
contain non-finite floats (NaN/inf) or exception objects in `ctx` produce a
200-serializable 422 response instead of a silent 500.
"""
from __future__ import annotations

import math

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, field_validator

from shared.validation import _sanitize, install_validation_handler


class _Model(BaseModel):
    epsilon: float

    @field_validator("epsilon")
    @classmethod
    def _finite_positive(cls, v: float) -> float:
        if not math.isfinite(v) or v <= 0:
            raise ValueError("epsilon must be a positive finite number")
        return v


def _app() -> FastAPI:
    app = FastAPI()
    install_validation_handler(app)

    @app.post("/x")
    async def _x(m: _Model) -> dict[str, float]:
        return {"epsilon": m.epsilon}

    return app


def test_nan_input_returns_422_not_500() -> None:
    c = TestClient(_app(), raise_server_exceptions=True)
    r = c.post(
        "/x",
        content=b'{"epsilon": NaN}',
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail[0]["loc"] == ["body", "epsilon"]
    assert detail[0]["input"] == "nan"


def test_value_error_ctx_is_serializable() -> None:
    c = TestClient(_app(), raise_server_exceptions=True)
    r = c.post("/x", json={"epsilon": -1.0})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail[0]["ctx"]["error"], dict)


def test_valid_body_unaffected() -> None:
    c = TestClient(_app(), raise_server_exceptions=True)
    r = c.post("/x", json={"epsilon": 1.5})
    assert r.status_code == 200
    assert r.json() == {"epsilon": 1.5}


@pytest.mark.parametrize(
    "raw,expected",
    [
        (float("nan"), "nan"),
        (float("inf"), "inf"),
        (float("-inf"), "-inf"),
        (1.5, 1.5),
        ({"a": [float("nan"), {"b": float("-inf")}]}, {"a": ["nan", {"b": "-inf"}]}),
    ],
)
def test_sanitize(raw: object, expected: object) -> None:
    assert _sanitize(raw) == expected
