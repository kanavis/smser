import pydantic
import yaml


class Device(pydantic.BaseModel):
    name: str
    device: str
    recipients: list[str]
    baudrate: int = 115200


class Config(pydantic.BaseModel):
    devices: list[Device]
    chats: dict[str, str]
    telegram_bot_token: str


def load_config_yaml(config: str) -> Config:
    return Config(**yaml.safe_load(config))
