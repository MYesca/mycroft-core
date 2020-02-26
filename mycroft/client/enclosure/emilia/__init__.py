# Copyright 2020 Marcello Yesca
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

import time
import sys
from threading import Timer

import mycroft.dialog
from mycroft.client.enclosure.base import Enclosure
from mycroft.api import has_been_paired
from mycroft.audio import wait_while_speaking
# from mycroft.enclosure.display_manager import \
#     init_display_manager_bus_connection
from mycroft.messagebus.message import Message
from mycroft.util import connected
from mycroft.util.log import LOG
from mycroft.configuration import Configuration, LocalConf, SYSTEM_CONFIG

from mycroft.client.enclosure.emilia.printer import PrinterCommand
from mycroft.client.enclosure.emilia.file_printer import FilePrinter


class EnclosureEmilia(Enclosure):
    """
    Serves as a communication interface between an old matrix printer and
    Mycroft Core.  This is used for Emilia, and/or for users of the CLI.
    """

    _last_internet_notification = 0

    def __init__(self):
        super().__init__()

        # Read the system configuration
        system_config = LocalConf(SYSTEM_CONFIG)
        printer_type = system_config.get("enclosure", {}).get("printer")

        if printer_type == "file":
            LOG.debug("Creating File printer")
            from mycroft.client.enclosure.emilia.file_printer import FilePrinter
            self.printer = FilePrinter(self.bus)
        else:
            LOG.debug("Creating Emilia printer")
            from mycroft.client.enclosure.emilia.emilia_printer import EmiliaPrinter
            self.printer = EmiliaPrinter(self.bus)

        self.printer.command(PrinterCommand.RESET)

        # Notifications from mycroft-core
        self.bus.on("enclosure.notify.no_internet", self.on_no_internet)
        self.bus.on("enclosure.printer.print.text", self.on_printText)
        self.bus.on("enclosure.printer.print.file", self.on_printFile)
        self.bus.on("enclosure.printer.command", self.on_printerCommand)

        # initiates the web sockets on display manager
        # NOTE: this is a temporary place to connect the display manager
        # init_display_manager_bus_connection()

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
        if "fancy" in event.data:
            if event.data["fancy"]:
                self.printer.command(PrinterCommand.LETTER_ON)
        if "expanded" in event.data:
            if event.data["expanded"]:
                self.printer.command(PrinterCommand.EXPANDED_ON)

        self.printer.print(bytearray(text, 'cp850', 'replace'))

        if "expanded" in event.data:
            if event.data["expanded"]:
                self.printer.command(PrinterCommand.EXPANDED_OFF)
        if "fancy" in event.data:
            if event.data["fancy"]:
                self.printer.command(PrinterCommand.LETTER_OFF)
        if "crlf" in event.data:
            if event.data["crlf"]:
                self.printer.command(PrinterCommand.NEW_LINE)

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
