import argparse
import datetime
import functools
import logging
import sys
import time
from pathlib import Path

import serial
import serial.threaded
import telebot

from smser.at_commands import ATProtocol
from smser.config import load_config_yaml
from smser.telegram_forwarder import TelegramForwarder
from smser.ussd import USSDCheckThread, USSDCheckTask

log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-file", type=Path, default=Path("config.yaml"))

    args = parser.parse_args()

    main_log = logging.getLogger()
    main_log.setLevel(logging.INFO)
    h = logging.StreamHandler(stream=sys.stdout)
    h.setLevel(logging.INFO)
    main_log.addHandler(h)

    with open(args.config_file, "r") as f:
        config = load_config_yaml(f.read())

    telegram_bot = telebot.TeleBot(token=config.telegram_bot_token)

    threads = []
    ussd_check_tasks: list[USSDCheckTask] = []
    for device in config.devices:
        log.info("Starting device {}".format(device))
        chat_ids = []
        for recipient in device.recipients:
            if recipient not in config.chats:
                raise RuntimeError("Wrong recipient {} in device {}".format(recipient, device))
            chat_ids.append(config.chats[recipient])
        port = serial.serial_for_url(device.device, baudrate=device.baudrate, timeout=5)
        forwarder_factory = functools.partial(
            TelegramForwarder, dev_name=device.name, telegram_bot=telegram_bot, chat_ids=chat_ids,
        )
        serial_thread = serial.threaded.ReaderThread(port, forwarder_factory)
        serial_thread.start()
        threads.append(serial_thread)

        def get_protocol() -> ATProtocol:
            start_at = datetime.datetime.now()
            status = "no_protocol"
            while True:
                if datetime.datetime.now() - start_at > datetime.timedelta(seconds=5):
                    raise RuntimeError("Device {} didn't connect for 5s (status={})".format(device.name, status))
                protocol = serial_thread.protocol
                if protocol is None:
                    continue
                status = "no_transport"
                assert isinstance(protocol, ATProtocol)
                if protocol.transport is not None:
                    break
                time.sleep(0.1)
            return protocol

        if device.balance_check is not None:
            ussd_check_tasks.append(USSDCheckTask(
                device_name=device.name,
                get_protocol=get_protocol,
                chats=chat_ids,
                code=device.balance_check.code,
                period_seconds=device.balance_check.period_days * 24 * 3600,
                hour_from=device.balance_check.hour_from,
                hour_till=device.balance_check.hour_till,
            ))

    if ussd_check_tasks:
        log.info("Starting USSD check thread")
        ussd_check_thread = USSDCheckThread(tasks=ussd_check_tasks, bot=telegram_bot)
        ussd_check_thread.start()
        threads.append(ussd_check_thread)

    log.info("Initialized. Reading")
    for thread in threads:
        thread.join()

    log.info("Exiting")
