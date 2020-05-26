import sys
import time
from PyQt5 import QtCore, QtWidgets
import DvG_QDeviceIO



class FakeDevice():
    def __init__(self):
        # Required members
        self.name = "FakeDev"
        self.mutex = QtCore.QMutex()
        self.is_alive = True
        
        # Member for testing
        self.counter = 0
        
    def set_alive(self, is_alive = True):
        self.is_alive = is_alive
    

    
def create_QApplication():
    QtCore.QThread.currentThread().setObjectName('MAIN')    # For DEBUG info

    app = 0    # Work-around for kernel crash when using Spyder IDE
    app = QtWidgets.QApplication(sys.argv)
    return app
    


def test_1():
    app = create_QApplication()
    
    # Simulate a device
    dev = FakeDevice()
    def DAQ_function():
        if dev.is_alive:
            dev.counter += 1
            print(dev.counter)
        return dev.is_alive
    #def alt_process_jobs_function(self, func, args):
        
    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    qdevio.attach_device(dev)
    
    qdevio.create_worker_DAQ(
        DAQ_update_interval_ms=100,
        DAQ_function_to_run_each_update=DAQ_function,
        DAQ_critical_not_alive_count=1,
        DAQ_timer_type=QtCore.Qt.CoarseTimer,
        DAQ_trigger_by=DvG_QDeviceIO.DAQ_trigger.INTERNAL_TIMER,
        calc_DAQ_rate_every_N_iter = 25,
        DEBUG=True)
    
    qdevio.create_worker_send()
    
    qdevio.start_thread_worker_DAQ()
    qdevio.start_thread_worker_send()
    
    # Simulate device runtime
    time.sleep(0.35)
    
    print("About to quit")
    app.processEvents()
    assert qdevio.close_thread_worker_DAQ() == True
    assert qdevio.close_thread_worker_send() == True
    app.quit()
    
    assert dev.counter == 3
    
    
    
if __name__ == "__main__":
    test_1()
    test_1()