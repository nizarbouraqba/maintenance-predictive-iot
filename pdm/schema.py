from datetime import datetime
from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

NUMERIC = ['air_temperature_k', 'process_temperature_k', 'rotational_speed_rpm', 'torque_nm', 'tool_wear_min']
FEATURES = ['type', *NUMERIC]
RENAME = dict(zip(['Type', 'Air temperature [K]', 'Process temperature [K]', 'Rotational speed [rpm]', 'Torque [Nm]', 'Tool wear [min]'], FEATURES))


class Telemetry(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    message_id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')
    machine_id: str = Field(default='SIM_AI4I', pattern=r'^[A-Za-z0-9_-]{1,64}$')
    sent_at: AwareDatetime
    measured_at: AwareDatetime | None = None  # AI4I ne fournit aucun timestamp physique.
    source_row: int = Field(ge=1)
    type: Literal['L', 'M', 'H']
    air_temperature_k: float = Field(gt=0)
    process_temperature_k: float = Field(gt=0)
    rotational_speed_rpm: float = Field(ge=0)
    torque_nm: float = Field(ge=0)
    tool_wear_min: float = Field(ge=0)


class Thresholds(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    critical: float = Field(default=0.7, gt=0, le=1)
    clear: float = Field(default=0.5, ge=0, lt=1)
    clear_count: int = Field(default=3, ge=1, le=100)

    @model_validator(mode='after')
    def valid_order(self):
        if self.clear >= self.critical:
            raise ValueError('Le seuil de retour doit être inférieur au seuil critique.')
        return self
