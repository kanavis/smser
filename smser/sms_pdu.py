import dataclasses
import datetime

from smspdudecoder.easy import read_incoming_sms


@dataclasses.dataclass
class SMS:
    storage: str
    number: int
    sender: str
    content: str
    date: datetime.datetime
    partial: bool


def read_incoming_sms_wrapped(pdu: str, storage: str, number: int) -> SMS:
    data = read_incoming_sms(pdu)
    return SMS(storage=storage, number=number, **data)
