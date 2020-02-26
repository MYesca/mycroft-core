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

import sys
from time import sleep
from threading import Thread
from queue import Queue
import gpiod

from mycroft.util.log import LOG
from mycroft.client.enclosure.emilia.printer import PrinterCommand
from mycroft.client.enclosure.emilia.printer import Printer

pBusy = 11   # 5              # parallel busy  PA11
pLatch = 12  # 3              # parallel latch PA12
sClock = 14  # 23             # serial clock   PA14
sData = 15   # 19             # serial data    PA15
sLatch = 16  # 21             # serial latch   PA16

GPIO_HIGH = 1
GPIO_LOW = 0


class EmiliaPrinter(Printer):

    def flush(self):
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
