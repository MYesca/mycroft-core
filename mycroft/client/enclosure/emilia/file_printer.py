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

from mycroft.util.log import LOG
from mycroft.client.enclosure.emilia.printer import Printer


class FilePrinter(Printer):

    def flush(self):
        with open("/var/log/mycroft/output.txt", mode="wb") as f:
            LOG.debug("File output opened")
            f.write(bytearray("Starting file output", 'cp850', 'replace'))
            while self.alive:
                try:
                    chunck = self.chuncks.get()
                    f.write(chunck)
                    f.flush()
                    self.chuncks.task_done()
                except Exception as e:
                    LOG.error("Unqueueing error: {0}".format(e))
