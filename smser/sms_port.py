import abc
import logging
import queue
import threading

from smser.at_commands import ATProtocol, ATException, ATEvent
from smser.sms_pdu import read_incoming_sms_wrapped, SMS

log = logging.getLogger(__name__)


class SMSPort(ATProtocol, abc.ABC):
    def __init__(self, dev_name: str):
        self._sms_queue = queue.Queue()
        super(SMSPort, self).__init__(dev_name=dev_name)
        self.start_forwarder_thread()

    def handle_parsed_event(self, parsed_event: ATEvent):
        if parsed_event.event_name == "+CMTI":
            storage = parsed_event.expect_arg(0, str)
            number = parsed_event.expect_arg(1, int)
            try:
                self.command("AT+CPMS=\"{}\"".format(storage))
            except ATException as err:
                log.error("AT protocol exception on set storage: {}".format(err))
                return
            try:
                sms_lines = [x.strip() for x in self.command("AT+CMGR={}".format(number)) if x.strip()]
            except ATException as err:
                log.error("AT protocol exception on read sms: {}".format(err))
                return
            if len(sms_lines) != 2:
                log.error("Wrong number of read SMS lines: {} (1 expected)".format(sms_lines))
                return
            try:
                sms = read_incoming_sms_wrapped(sms_lines[1], storage, number)
            except Exception as err:
                log.error("SMS read exception on read SMS lines ({}): {}".format(sms_lines, err))
                return

            self._sms_queue.put(sms)

    def run(self):
        while self.alive:
            try:
                sms = self._sms_queue.get(timeout=1)
            except queue.Empty:
                continue
            self.handle_sms(sms)

    def start_forwarder_thread(self) -> threading.Thread:
        thread = threading.Thread(target=self.run, daemon=True, name="at-sms-{}".format(self._dev_name))
        thread.start()
        return thread

    @abc.abstractmethod
    def handle_sms(self, sms: SMS):
        pass
