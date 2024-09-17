import dataclasses
import datetime
import logging
import threading
import time
from collections import deque
from typing import Optional, Deque, Callable

import telebot

from smser.at_commands import ATProtocol, ATException, ATEventSubscription, ATEvent

log = logging.getLogger(__name__)


@dataclasses.dataclass
class USSDCheckTask:
    device_name: str
    get_protocol: Callable[[], ATProtocol]
    chats: list[str]
    code: str
    period_seconds: int
    hour_from: Optional[int]
    hour_till: Optional[int]
    last: Optional[datetime.datetime] = None


@dataclasses.dataclass
class Message:
    chat: str
    msg: str
    debug_info: str


class USSDSubscription(ATEventSubscription):
    def __init__(self, on_message: Callable[[str], None]):
        super().__init__()
        self._on_message = on_message

    def process_event(self, event: ATEvent):
        if event.event_name != "+CUSD":
            return
        self.unsubscribe()
        cmd = event.expect_arg(0, int)
        if cmd not in (0, 1):
            log.warning("Received CUSD with unknown status %s", event)
            return
        self._on_message(event.expect_arg(1, str))


class USSDCheckThread(threading.Thread):
    def __init__(self, tasks: list[USSDCheckTask], bot: telebot.TeleBot):
        super().__init__(daemon=True)
        self.bot = bot
        self.tasks = tasks
        self.delayed_messages: Deque[Message] = deque()

    def send_message(self, message: Message):
        try:
            self.bot.send_message(message.chat, message.msg)
        except Exception:
            log.exception("Exception sending {} to chat {}".format(message.debug_info, message.chat))
            self.delayed_messages.append(message)

    def run_task(self, task: USSDCheckTask):
        log.info("Running USSD task '{}' for device '{}'".format(task.code, task.device_name))
        cmd = 'AT+CUSD=1,"{}",15'.format(task.code)

        def on_message(base_msg: str):
            log.info("Closing USSD session for task '{}' device '{}'".format(task.code, task.device_name))
            try:
                task.get_protocol().command("AT+CUSD=2")
            except ATException as e:
                log.warning("Error closing USSD session for task '{}' device '{}': {}".format(
                    task.code, task.device_name, e,
                ))
            msg = "Regular balance check for '{}' at {}:\n{}".format(
                task.device_name,
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                base_msg,
            )
            for chat in task.chats:
                self.send_message(Message(
                    chat=chat,
                    msg=msg,
                    debug_info="USSD task '{}' for device '{}' result".format(task.code, task.device_name),
                ))

        try:
            task.get_protocol().command(cmd, subscribe=USSDSubscription(on_message=on_message))
        except ATException as err:
            log.error("Error sending USSD code '{}' to '{}: {}".format(task.code, task.device_name, err))
            return
        task.last = datetime.datetime.now()

    def _run(self):
        for task in self.tasks:
            now = datetime.datetime.now()
            if (
                (task.hour_from is None or now.hour >= task.hour_from) and
                (task.hour_till is None or now.hour < task.hour_till) and
                (task.last is None or task.last + datetime.timedelta(seconds=task.period_seconds) <= now)
            ):
                self.run_task(task)
        for message in self.delayed_messages:
            self.send_message(message)

    def run(self):
        try:
            while True:
                self._run()
                time.sleep(1)
        except Exception:
            log.exception("Exception in USSD check thread")
