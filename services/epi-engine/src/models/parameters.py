from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class SEIRParameterBase(BaseModel):
    beta: float = Field(..., gt=0, le=5.0)
    sigma: float = Field(..., gt=0.05, le=2.0)
    gamma: float = Field(..., gt=0.02, le=1.0)
    rho: float = Field(default=1.0, gt=0, le=1.0)
    fA: float = Field(..., gt=0, le=1.0)
    fM: float = Field(..., gt=0, le=1.0)
    fS: float = Field(..., gt=0, le=1.0)
    alpha: float = Field(..., gt=0, le=1.0)
    h_rate: float = Field(..., gt=0, le=1.0)
    delta: float = Field(..., gt=0, le=1.0)
    mu: float = Field(..., gt=0, le=1.0)
    mu_icu: float = Field(..., gt=0, le=1.0)
    gamma_A: float = Field(..., gt=0, le=1.0)
    gamma_M: float = Field(..., gt=0, le=1.0)
    gamma_S: float = Field(..., gt=0, le=1.0)
    gamma_H: float = Field(..., gt=0, le=1.0)
    gamma_ICU: float = Field(..., gt=0, le=1.0)
    papp: float = Field(default=0.12, gt=0, le=1.0)
    N_pop: int = Field(..., ge=1000, le=10_000_000_000)

    @model_validator(mode='after')
    def validate_fractions(self) -> 'SEIRParameterBase':
        if abs(self.fA + self.fM + self.fS - 1.0) > 1e-6:
            raise ValueError("fA + fM + fS must sum to 1.0")
        return self

class RegionParams(SEIRParameterBase):
    region_id: str
    source: str = Field(..., pattern='^(ekf_estimate|manual_override)$')
    updated_at: datetime | None = None

class ForecastRequest(BaseModel):
    horizon_days: int = Field(default=14, ge=7, le=21)
    include_uncertainty: bool = Field(default=False)

class ForecastResponse(BaseModel):
    region_id: str
    generated_at: datetime
    horizon_days: int
    trajectory: dict # {t:[], S:[], E:[], IA:[], IM:[], IS:[], H:[], ICU:[], R:[], D:[], Load:[]}
    params_hash: str
