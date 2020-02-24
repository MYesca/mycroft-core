# Copyright 2017 Mycroft AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import subprocess
import time
from time import sleep
import sys
from alsaaudio import Mixer
from threading import Thread, Timer

import mycroft.dialog
from mycroft.client.enclosure.base import Enclosure
from mycroft.api import has_been_paired
from mycroft.audio import wait_while_speaking
from mycroft.enclosure.display_manager import \
    init_display_manager_bus_connection
from mycroft.messagebus.message import Message
from mycroft.util import connected
from mycroft.util.log import LOG
from queue import Queue
import gpiod #Pi.GPIO as GPIO
from enum import Flag, auto

pBusy = 11 #5               # parallel busy  PA11
pLatch = 12 #3              # parallel latch PA12
sClock = 14 #23             # serial clock   PA14
sData = 15 #19              # serial data    PA15
sLatch = 16 #21             # serial latch   PA16

GPIO_HIGH = 1
GPIO_LOW = 0

class PrinterCommand(Flag):
    RESET = auto()
    NEW_LINE = auto()
    LETTER_ON = auto()
    LETTER_OFF = auto()
    UNDERLINE_ON = auto()
    UNDERLINE_OFF = auto()
    SUPERSCRIPT_ON = auto()
    SUPERSCRIPT_OFF = auto()
    SUBSCRIPT_ON = auto()
    SUBSCRIPT_OFF = auto()
    CONDENSED_ON = auto()
    CONDENSED_OFF = auto()
    EXPANDED_ON = auto()
    EXPANDED_OFF = auto()


class EnclosurePrinter(Thread):
    """
    Writes data to Printer port.
        #. Enqueues all commands received from Mycroft enclosures
           implementation
        #. Process them on the received order by writing on the Printer port
    """

    def __init__(self, bus, size=16):
        super(EnclosurePrinter, self).__init__(target=self.flush)
        self.alive = True
        self.daemon = True
        self.bus = bus
        self.chuncks = Queue(size)
        self.bus.on("mycroft.stop", self.stop)
        LOG.debug("Starting printer thread")
        self.start()

    def flush(self):
        try:

            with gpiod.Chip("gpiochip0") as chip:
                lines = {
                        "pBusy": chip.get_line(pBusy),
                        "sData": chip.get_line(sData),
                        "sClock": chip.get_line(sClock),
                        "sLatch": chip.get_line(sLatch),
                        "pLatch": chip.get_line(pLatch)
                        }
                lines["pBusy"].request(consumer="emilia", type=gpiod.LINE_REQ_DIR_IN)
                lines["sData"].request(consumer="emilia", type=gpiod.LINE_REQ_DIR_OUT)
                lines["sClock"].request(consumer="emilia", type=gpiod.LINE_REQ_DIR_OUT)
                lines["sLatch"].request(consumer="emilia", type=gpiod.LINE_REQ_DIR_OUT)
                lines["pLatch"].request(consumer="emilia", type=gpiod.LINE_REQ_DIR_OUT)

                while self.alive:
                    try:
                        chunck = self.chuncks.get()
                        self.__write__(lines, chunck)
                        self.chuncks.task_done()
                    except Exception as e:
                        LOG.error("Unqueueing error: {0}".format(e))
        finally:
            pass

    def __write__(self, lines, chunck):
        try:
            for byte in chunck:
                self.__writeByte__(lines, byte)
                sleep(0.01)
        except Exception as e:
            LOG.error("Writing error: {0}".format(e))

    def __writeByte__(self, lines, value):   # MSB out first!
        while lines["pBusy"].get_value() == GPIO_HIGH:
            sleep(0.01)
        for x in range(0, 8):
            temp = value & 0x80
            if temp == 0x80:
                lines["sData"].set_value(GPIO_HIGH)
            else:
                lines["sData"].set_value(GPIO_LOW)
            lines["sClock"].set_value(GPIO_HIGH)
            lines["sClock"].set_value(GPIO_LOW)
            value = value << 0x01                        # shift left
        lines["sLatch"].set_value(GPIO_LOW)
        sleep(0.001)
        lines["sLatch"].set_value(GPIO_HIGH)
        lines["pLatch"].set_value(GPIO_LOW)
        sleep(0.001)
        lines["pLatch"].set_value(GPIO_HIGH)

    def print(self, chunck):
        self.chuncks.put(chunck)
    
    def command(self, cmd):
        if cmd == PrinterCommand.RESET:
            chunck = b'\x1B\x40\x1B\x51\x50' #\x1B\x43\x5A form size 90
        elif cmd == PrinterCommand.NEW_LINE:
            chunck = b'\x0A'
        elif cmd == PrinterCommand.LETTER_ON:
            chunck = b'\x1B\x47'
        elif cmd == PrinterCommand.LETTER_OFF:
            chunck = b'\x1B\x48'
        elif cmd == PrinterCommand.UNDERLINE_ON:
            chunck = b'\x1B\x5F\x01'
        elif cmd == PrinterCommand.UNDERLINE_OFF:
            chunck = b'\x1B\x5F\x00'
        elif cmd == PrinterCommand.SUPERSCRIPT_ON:
            chunck = b'\x1B\x53\x00'
        elif cmd == PrinterCommand.SUPERSCRIPT_OFF:
            chunck = b'\x1B\x54'
        elif cmd == PrinterCommand.SUBSCRIPT_ON:
            chunck = b'\x1B\x53\x01'
        elif cmd == PrinterCommand.SUBSCRIPT_OFF:
            chunck = b'\x1B\x54'
        elif cmd == PrinterCommand.CONDENSED_ON:
            chunck = b'\x0F'
        elif cmd == PrinterCommand.CONDENSED_OFF:
            chunck = b'\x12'
        elif cmd == PrinterCommand.EXPANDED_ON:
            chunck = b'\x1B\x57\x01'
        elif cmd == PrinterCommand.EXPANDED_OFF:
            chunck = b'\x1B\x57\x00'
        else:
            chunck = None

        if chunck != None:
            self.chuncks.put(chunck)

    def stop(self):
        self.alive = False


class EnclosureEmilia(Enclosure):
    """
    Serves as a communication interface between an old matrix printer and
    Mycroft Core.  This is used for Emilia, and/or for users of the CLI.
    """

    _last_internet_notification = 0

    def __init__(self):
        super().__init__()

        self.printer = EnclosurePrinter(self.bus)
        self.printer.command(PrinterCommand.RESET)

        # Notifications from mycroft-core
        self.bus.on("enclosure.notify.no_internet", self.on_no_internet)
        self.bus.on("enclosure.printer.print.text", self.on_printText)
        self.bus.on("enclosure.printer.print.file", self.on_printFile)
        self.bus.on("enclosure.printer.command", self.on_printerCommand)

        # initiates the web sockets on display manager
        # NOTE: this is a temporary place to connect the display manager
        init_display_manager_bus_connection()

        # verify internet connection and prompt user on bootup if needed
        if not connected():
            # We delay this for several seconds to ensure that the other
            # clients are up and connected to the messagebus in order to
            # receive the "speak".  This was sometimes happening too
            # quickly and the user wasn't notified what to do.
            Timer(5, self._do_net_check).start()

    def on_no_internet(self, event=None):
        if connected():
            # One last check to see if connection was established
            return

        if time.time() - Enclosure._last_internet_notification < 30:
            # don't bother the user with multiple notifications with 30 secs
            return

        Enclosure._last_internet_notification = time.time()

        # TODO: This should go into EnclosureMark1 subclass of Enclosure.
        if has_been_paired():
            # Handle the translation within that code.
            self.speak("This device is not connected to the Internet. "
                       "Either plug in a network cable or set up your "
                       "wifi connection.")
        else:
            # enter wifi-setup mode automatically
            self.bus.emit(Message('system.wifi.setup', {'lang': self.lang}))

    def on_printText(self, event=None):
        text = event.data["text"]
        if event.data["fancy"]: self.printer.command(PrinterCommand.LETTER_ON)
        if event.data["expanded"]: self.printer.command(PrinterCommand.EXPANDED_ON)
        self.printer.print(bytearray(text, 'cp850', 'replace'))
        if event.data["expanded"]: self.printer.command(PrinterCommand.EXPANDED_OFF)
        if event.data["fancy"]: self.printer.command(PrinterCommand.LETTER_OFF)
        if event.data["crlf"]: self.printer.command(PrinterCommand.NEW_LINE)

    def on_printFile(self, event=None):
        with open(event.data["file"], mode="rb") as f:
            chunck = f.read(1000)
            while chunck:
                self.printer.print(chunck)
                chunck = f.read(1000)

    def on_printerCommand(self, event=None):
        self.printer.command(PrinterCommand[event.data["cmd"]])

    def speak(self, text):
        self.bus.emit(Message("speak", {'utterance': text}))

    def _handle_pairing_complete(self, Message):
        """
        Handler for 'mycroft.paired', unmutes the mic after the pairing is
        complete.
        """
        self.bus.emit(Message("mycroft.mic.unmute"))

    def _do_net_check(self):
        # TODO: This should live in the derived Enclosure, e.g. EnclosureMark1
        LOG.info("Checking internet connection")
        if not connected():  # and self.conn_monitor is None:
            if has_been_paired():
                # TODO: Enclosure/localization
                self.speak("This unit is not connected to the Internet. "
                           "Either plug in a network cable or setup your "
                           "wifi connection.")
            else:
                # Begin the unit startup process, this is the first time it
                # is being run with factory defaults.

                # TODO: This logic should be in EnclosureMark1
                # TODO: Enclosure/localization

                # Don't listen to mic during this out-of-box experience
                self.bus.emit(Message("mycroft.mic.mute"))
                # Setup handler to unmute mic at the end of on boarding
                # i.e. after pairing is complete
                self.bus.once('mycroft.paired', self._handle_pairing_complete)

                self.speak(mycroft.dialog.get('mycroft.intro'))
                wait_while_speaking()
                time.sleep(2)  # a pause sounds better than just jumping in

                # Kick off wifi-setup automatically
                data = {'allow_timeout': False, 'lang': self.lang}
                self.bus.emit(Message('system.wifi.setup', data))
