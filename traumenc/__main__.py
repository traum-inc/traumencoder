#!/usr/bin/env python
import sys
import multiprocessing
from PyQt5.QtWidgets import QApplication

from engine import create_engine
from mainwindow import MainWindow
from utils import setup_logging
import logging

log = logging.getLogger('app')

if __name__ == '__main__':
    # enable frozen module support for Windows installer
    multiprocessing.freeze_support()

    # if frozen, cd to the bundle dir
    if getattr(sys, 'frozen', False):
        bundle_dir = sys._MEIPASS
        os.chdir(bundle_dir)

    setup_logging(color=True)
    app = QApplication(sys.argv)

    # start the engine
    log.debug('starting engine')
    engine = create_engine()

    # create my widgets
    main = MainWindow(engine)
    main.show()

    # start the app
    rc = app.exec_()

    # stop the engine
    log.debug('joining engine')
    engine.join()

    # quit
    sys.exit(rc)
