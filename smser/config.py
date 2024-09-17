from typing import Optional

import pydantic
import yaml


class BalanceCheck(pydantic.BaseModel):
    period_days: int
    code: str
    hour_from: Optional[int] = 10
    hour_till: Optional[int] = 23


class Device(pydantic.BaseModel):
    name: str
    device: str
    recipients: list[str]
    baudrate: int = 115200
    balance_checks: list[BalanceCheck] = pydantic.field(default_factory=list)


class Config(pydantic.BaseModel):
    devices: list[Device]
    chats: dict[str, str]
    telegram_bot_token: str


def load_config_yaml(config: str) -> Config:
    return Config.model_validate(yaml.safe_load(config))
