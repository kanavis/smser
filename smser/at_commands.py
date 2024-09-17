import abc
import dataclasses
import logging
from typing import TypeVar, Type, Optional

import serial.threaded
import threading
import queue

log = logging.getLogger(__name__)
T = TypeVar("T")

EXIT = object()


class ATException(Exception):
    pass


@dataclasses.dataclass
class ATEvent:
    event_name: str
    args: list[int | str | float]

    def expect_arg(self, arg_idx: int, t: Type[T]) -> T:
        try:
            arg = self.args[arg_idx]
        except IndexError:
            raise ATException("Expected argument {} as {} for event {}".format(arg_idx, t, self))
        if not isinstance(arg, t):
            raise ATException("Expected argument {} as {} for event {}".format(arg_idx, t, self))
        return arg


class ATEventSubscription(abc.ABC):
    def __init__(self):
        self.subscribed = True

    def unsubscribe(self):
        self.subscribed = False

    @abc.abstractmethod
    def process_event(self, event: ATEvent):
        pass


class ATProtocol(serial.threaded.LineReader, abc.ABC):

    TERMINATOR = b"\r\n"

    def __init__(self, dev_name: str):
        super(ATProtocol, self).__init__()
        self._dev_name = dev_name
        self.alive = True
        self.responses = queue.Queue()
        self.events = queue.Queue()
        self._event_thread = threading.Thread(target=self._run_event)
        self._event_thread.daemon = True
        self._event_thread.name = "at-event-{}".format(dev_name)
        self._event_thread.start()
        self._subscriptions: list[ATEventSubscription] = []
        self.lock = threading.Lock()

    def stop(self):
        """
        Stop the event processing thread, abort pending commands, if any.
        """
        self.alive = False
        self.events.put(None)
        self.responses.put(EXIT)

    def _run_event(self):
        """
        Process events in a separate thread so that input thread is not
        blocked.
        """
        while self.alive:
            try:
                self.handle_event(self.events.get(timeout=1))
            except queue.Empty:
                continue
            except Exception:
                logging.exception("_run_event {}".format(self._dev_name))

    def handle_line(self, line: str):
        """
        Handle input from serial port, check for events.
        """
        if line.startswith("+"):
            self.events.put(line)
        else:
            self.responses.put(line)

    def _process_at_arg(self, arg: str) -> int | str | float:
        if arg.startswith('"') and arg.endswith('"'):
            return arg[1:-1]
        else:
            try:
                return int(arg)
            except ValueError:
                try:
                    return float(arg)
                except ValueError:
                    return arg

    def parse_at_event(self, event: str) -> ATEvent:
        event = event.strip()
        if ":" not in event:
            raise ATException("Invalid AT event: '{}'".format(event))
        event_name, args_str = event.split(":", 1)
        args = [self._process_at_arg(x.strip()) for x in args_str.split(",")]
        return ATEvent(event_name, args)

    @abc.abstractmethod
    def handle_parsed_event(self, parsed_event: ATEvent):
        pass

    def handle_event(self, event: str):
        """
        Spontaneous message received.
        """
        log.info("Received event: '%s'", event.strip())
        try:
            parsed_event = self.parse_at_event(event)
        except ATException as err:
            log.error("AT protocol exception on event: {}".format(err))
            return
        self.handle_parsed_event(parsed_event)
        self._subscriptions = [x for x in self._subscriptions if x.subscribed]
        for subscription in self._subscriptions:
            subscription.process_event(parsed_event)

    def command(
        self,
        command: str,
        response="OK",
        err_response="ERROR",
        timeout=5,
        subscribe: Optional[ATEventSubscription] = None,
    ) -> list[str]:
        """
        Set an AT command and wait for the response.
        """
        with self.lock:  # ensure that just one thread is sending commands at once
            if subscribe is not None:
                self._subscriptions.append(subscribe)
            self.write_line(command)
            lines = []
            while True:
                try:
                    line = self.responses.get(timeout=timeout)
                    if line is EXIT:
                        raise ATException("Port closed")
                    if line == response:
                        return lines
                    elif line == err_response:
                        raise ATException("Error for command ('{}'): {}".format(command, "\n".join(lines)))
                    else:
                        lines.append(line)
                except queue.Empty:
                    raise ATException("AT command timeout ('{}') (received: {})".format(command, lines))
