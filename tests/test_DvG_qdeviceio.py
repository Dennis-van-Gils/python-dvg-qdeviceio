import DvG_QDeviceIO
from PyQt5 import QtCore, QtWidgets as QtWid
import time
import sys

from unittest import mock
import io



class Counter():
    val = 0
counter = Counter()



def print_counter():
    print(counter.val)
    counter.val += 1
    return True



    
def create_QApplication():
    QtCore.QThread.currentThread().setObjectName('MAIN')    # For DEBUG info

    app = 0    # Work-around for kernel crash when using Spyder IDE
    app = QtWid.QApplication(sys.argv)
    return app
    


def test_defaults_Worker_DAQ():
    app = create_QApplication()
    qdevio = DvG_QDeviceIO.QDeviceIO()
    
    # Simulate a device
    qdevio.dev.name = "FakeDev"
    qdevio.dev.is_alive = True
    
    qdevio.create_worker_DAQ(
        DAQ_update_interval_ms=1000,
        DAQ_function_to_run_each_update=print_counter,
        DAQ_critical_not_alive_count=1,
        DAQ_timer_type=QtCore.Qt.CoarseTimer,
        DAQ_trigger_by=DvG_QDeviceIO.DAQ_trigger.INTERNAL_TIMER,
        calc_DAQ_rate_every_N_iter = 25,
        DEBUG=True)
    
    qdevio.start_thread_worker_DAQ()
    
    time.sleep(3.5)
    
    print("About to quit")
    app.processEvents()
    qdevio.close_thread_worker_DAQ()    
    app.quit()
    
if __name__ == "__main__":
    test_defaults_Worker_DAQ()
    
    test_defaults_Worker_DAQ()