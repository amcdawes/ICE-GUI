#!python3.5
__author__ = 'Vescent Photonics, Inc.'
__version__ = '1.2'

# NOTE: PyQt5 depends on DirectX for doing OpenGL graphics, so
# the deployment machine may require the Microsoft DirectX runtime
# to be installed for the application to start.

import sys
import os
import logging
from PyQt5.QtCore import *
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from PyQt5 import QtQuick
from PyQt5.QtQml import QJSValue
import iceComm
from xml.etree import ElementTree   
from urllib.request import urlopen
from collections import defaultdict
import json

# Converts XML ElementTree to Python dict
def etree_to_dict(t):
    d = {t.tag: {} if t.attrib else None}
    children = list(t)
    if children:
        dd = defaultdict(list)
        for dc in map(etree_to_dict, children):
            for k, v in dc.items():
                dd[k].append(v)
        d = {t.tag: {k:v[0] if len(v) == 1 else v for k, v in dd.items()}}
    if t.attrib:
        d[t.tag].update(('@' + k, v) for k, v in t.attrib.items())
    if t.text:
        text = t.text.strip()
        if children or t.attrib:
            if text:
              d[t.tag]['#text'] = text
        else:
            d[t.tag] = text
    return d

class PyConsole(QObject):
    def __init__(self, version):
        super().__init__()
        self.version_str = version

    @pyqtSlot(str)
    def log(self, s):
        logging.info('QML: ' + s)

    @pyqtProperty(str)
    def version(self):
        return self.version_str

    @pyqtSlot(str, str)
    def writeFile(self, filename, data):
        file = open(filename, 'w')
        file.write(data)
        file.close()

    @pyqtSlot(str, result=str)
    def readFile(self, filename):
        file = open(filename, 'r')
        data = file.read()
        file.close()
        return data        
        
    @pyqtSlot(str, result=QVariant)
    def getXML(self, source_url):
        data = {}
        
        try:
            usock = urlopen(source_url)
            tree = ElementTree.parse(usock)
            usock.close()             
        except:
            tree = None           
         
        if (tree):
            data = etree_to_dict(tree.getroot())
            
        return QVariant(data)


class iceController(QObject):
    def __init__(self):
        super().__init__()
        self.slot = 0
        self._logging = False
        self.iceRef = iceComm.Connection(log=False)

    @pyqtSlot(int)
    def setSlot(self, slot):
        if slot != self.slot:
            self.iceRef.send('#slave ' + str(slot))
            self.slot = slot

    @pyqtSlot(str, int, 'QJSValue', result=str)
    def send(self, command, slot, callback):
        if slot != self.slot:
            self.iceRef.send('#slave ' + str(slot))
            self.slot = slot

        data = self.iceRef.send(command)

        if data[:9] == 'I2C Error':
            logging.error(command)
            logging.error('Error I2c!!!')
            return

        if callback.isCallable():
            callback.call({data})

        return data

    @pyqtSlot(str, 'QJSValue')
    def enqueue(self, command, callback):
        self.iceRef.send(command, blocking=False, callback=QJSValue(callback))
        return

    @pyqtSlot()
    def processResponses(self):
        responses = self.iceRef.get_all_responses()

        for response in responses:
            cbFunc = response.get('callback', None)

            if cbFunc is not None:
                self.callback = cbFunc

                if cbFunc.isCallable():
                    cbFunc.call({response['result'].rstrip()})

        return

    @pyqtSlot()
    def getResponses(self):
        responses = self.iceRef.get_all_responses()
        if len(responses) > 0:
            return responses[0]['callback']

    @pyqtSlot(str, result=bool)
    def serialOpen(self, portname):
        result = self.iceRef.connect(portname, timeout=0.5)
        if result is None:
            return True
        else:
            logging.error(result)
            return False

    @pyqtSlot(bool)
    def setLogging(self, enabled):
        self.iceRef.logging = enabled
        self._logging = enabled

    @pyqtProperty(bool)
    def logging(self):
        return self._logging

    @pyqtSlot()
    def serialClose(self):
        self.iceRef.disconnect()

    @pyqtSlot(result='QVariant')
    def getSerialPorts(self):
        ports = self.iceRef.list_serial_ports()
        portnames = []
        for port in ports:
            portnames.append(port[0])

        return portnames

    @pyqtSlot(str, 'QVariant')
    def saveData(self, file_path, file_data):
        file_path = file_path.lstrip("file:///")
        with open(file_path, 'w') as f:
            # f.write("OLOL")
            f.write(json.dumps(file_data.toVariant(), sort_keys=True, indent=4, separators=(',', ': ')))

    @pyqtSlot(str, result='QVariant')
    def loadData(self, file_path):
        file_path = file_path.lstrip("file:///")
        data = {}
        with open(file_path, 'r') as f:
            data = json.loads(f.read())
            print(data)
        return data



class StreamToLogger(object):
    """
    Fake file-like stream object that redirects writes to a logger instance.
    """

    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())

    def flush(self):
        pass


def main():
    logging.basicConfig(filename='log.txt',
                        level=logging.DEBUG,
                        filemode='w')

    # Redirect stdout and stderr to our logging file
    stdout_logger = logging.getLogger('STDOUT')
    stderr_logger = logging.getLogger('STDERR')
    sys.stdout = StreamToLogger(stdout_logger, logging.INFO)
    sys.stderr = StreamToLogger(stderr_logger, logging.ERROR)

    logging.info('Started ICE Control v' + __version__)

    app = QApplication(sys.argv)

    app_name = 'ICE Control'
    app.setOrganizationName("Vescent Photonics, Inc.")
    app.setOrganizationDomain("www.vescent.com")
    app.setApplicationName(app_name)
    app.setWindowIcon(QIcon("ui/vescent.ico"))

    view = QtQuick.QQuickView()

    if getattr(sys, 'frozen', False):
        # we are running in a |PyInstaller| bundle
        basedir = sys._MEIPASS
    else:
        # we are running in a normal Python environment
        basedir = os.path.dirname(os.path.abspath(__file__))

    view.setTitle(app_name)
    context = view.rootContext()

    pyconsole = PyConsole(__version__)
    context.setContextProperty('python', pyconsole)

    ice = iceController()
    context.setContextProperty('ice', ice)

    view.setSource(QUrl("ui/main.qml"))
    view.engine().quit.connect(app.quit)
    view.show()

    app.exec_()

    #Cleanup: Manually delete QQuickView to prevent app crash
    del view
    ice.iceRef.disconnect()
    sys.exit(0)

if __name__ == "__main__":
    main()
