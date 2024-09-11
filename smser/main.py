import argparse
import functools
import logging
import sys
from pathlib import Path

import serial
import serial.threaded
import telebot

from smser.config import load_config_yaml
from smser.telegram_forwarder import TelegramForwarder

log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-file-path", type=Path, default=Path("config.yaml"))

    args = parser.parse_args()

    main_log = logging.getLogger()
    main_log.setLevel(logging.INFO)
    h = logging.StreamHandler(stream=sys.stdout)
    h.setLevel(logging.INFO)
    main_log.addHandler(h)

    config = load_config_yaml(args.config_file.read())

    telegram_bot = telebot.TeleBot(token=config.telegram_token)

    threads = []
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

    log.info("Initialized. Reading")
    for thread in threads:
        thread.join()

    log.info("Exiting")
