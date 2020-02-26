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

from threading import Thread
from queue import Queue
from enum import Flag, auto

from mycroft.util.log import LOG


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


class Printer(Thread):
    """
    Writes data to Printer port.
        #. Enqueues all commands received from Mycroft enclosures
           implementation
        #. Process them on the received order by writing on the Printer port
    """

    def __init__(self, bus, size=16):
        super(Printer, self).__init__(target=self.flush)
        self.alive = True
        self.daemon = True
        self.bus = bus
        self.chuncks = Queue(size)
        self.bus.on("mycroft.stop", self.stop)
        LOG.debug("Starting printer thread")
        self.start()

    def flush(self):
        raise NotImplementedError

    def print(self, chunck):
        self.chuncks.put(chunck)

    def command(self, cmd):
        if cmd == PrinterCommand.RESET:
            chunck = b'\x1B\x40\x1B\x51\x50'  # \x1B\x43\x5A form size 90
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

        if chunck is not None:
            self.chuncks.put(chunck)

    def stop(self):
        self.alive = False
