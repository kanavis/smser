import logging
from logging import exception

import telebot

from smser.sms_pdu import SMS
from smser.sms_port import SMSPort

log = logging.getLogger(__name__)


class TelegramForwarder(SMSPort):
    def __init__(self, dev_name: str, telegram_bot: telebot.TeleBot, chat_ids: list[str]):
        self._bot = telegram_bot
        self._chat_ids = chat_ids
        super().__init__(dev_name=dev_name)

    def handle_sms(self, sms: SMS):
        log.info("Received SMS message {}. Sending to chats {}".format(sms, self._chat_ids))
        for chat_id in self._chat_ids:
            try:
                self._bot.send_message(
                    chat_id=chat_id,
                    text="SMS to {} from {} at {}:\n{}".format(
                    self._dev_name, sms.sender, sms.date.strftime("%Y-%m-%d %H:%M:%S"), sms.content,
                    ),
                )
            except Exception as err:
                log.info("Error sending message {} to chat {}: {}".format(sms, chat_id, err))
