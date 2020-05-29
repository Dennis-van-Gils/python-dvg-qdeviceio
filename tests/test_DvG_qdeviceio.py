import sys
import time
from PyQt5 import QtCore, QtWidgets
import DvG_QDeviceIO


"""TODO: Separate FakeDevice into multiple versions, like:

DAQ_trigger.INTERNAL_TIMER
    I/O device slaved to an external timer originating from Worker_DAQ

DAQ_trigger.EXTERNAL_WAKE_UP_CALL
    Typical use case: Multiple I/O devices that are slaved to a common single
    external timer originating from a higher scope Python module than 
    this 'DvG_QdeviceIO' module.
    See Keysight_N8700_PSU for an example.
    
    def simultaneously_trigger_update_multiple_devices():
        for qdevio in qdevios:
            qdevio.worker_DAQ.wake_up()
            
    timer_qdevios = QtCore.QTimer()
    timer_qdevios.timeout.connect(simultaneously_trigger_update_multiple_devices)
    timer_qdevios.start(UPDATE_INTERVAL_MS)

DAQ_trigger.CONTINUOUS
    Typical use case: I/O device acting as a master and outputting a continuous
    stream of data. The worker_DAQ will start up in suspended mode (idling).
    This allows for a start command to be send to the I/O device, for instance,
    over a Worker_Send instance. Once the start command has been received and
    processed by the device, such that it will output a continuous stream of
    data, worker_DAQ can be taken out of suspended mode and have it listen and
    receive this data stream.
    
    
    
"""

# FakeDevice_master_of_...
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
    
    def fake_query(self):
        self.counter += 1
        return self.counter


    
def create_QApplication():
    QtCore.QThread.currentThread().setObjectName('MAIN')    # For DEBUG info
    app = 0     # Work-around for kernel crash when using Spyder IDE
    app = QtWidgets.QApplication(sys.argv)
    return app
    


def test_Worker_DAQ__INTERNAL_TIMER():
    print("\nTEST Worker_DAQ INTERNAL_TIMER")
    print("------------------------------")
    app = create_QApplication()
    
    # Simulate a device
    dev = FakeDevice()
    def DAQ_function():
        if dev.is_alive:
            dev.counter += 1
            print(dev.counter)
        return dev.is_alive
    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    qdevio.attach_device(dev)
    
    # Worker_DAQ in mode INTERNAL TIMER
    qdevio.create_worker_DAQ(
        DAQ_trigger_by                  = DvG_QDeviceIO.DAQ_trigger.INTERNAL_TIMER,
        DAQ_function_to_run_each_update = DAQ_function,
        DAQ_update_interval_ms          = 100,
        DAQ_timer_type                  = QtCore.Qt.CoarseTimer,
        DAQ_critical_not_alive_count    = 1,
        calc_DAQ_rate_every_N_iter      = 5,
        DEBUG                           = True)
    qdevio.start_worker_DAQ()
    
    # Simulate device runtime
    time.sleep(.35)
    
    print("About to quit")
    app.processEvents()
    assert qdevio.quit_worker_DAQ() == True
    app.quit()
    
    assert dev.counter == 3

    

def test_Worker_DAQ__CONTINUOUS():
    print("\nTEST Worker_DAQ CONTINUOUS")
    print("--------------------------")
    app = create_QApplication()
    
    # Simulate a device
    dev = FakeDevice()
    def DAQ_function():
        if dev.is_alive:
            dev.counter += 1
            print(dev.counter)
            time.sleep(.1)
        return dev.is_alive        
    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    qdevio.attach_device(dev)
    
    # Worker_DAQ in mode CONTINUOUS
    qdevio.create_worker_DAQ(
        DAQ_trigger_by                  = DvG_QDeviceIO.DAQ_trigger.CONTINUOUS,
        DAQ_function_to_run_each_update = DAQ_function,
        DAQ_critical_not_alive_count    = 1,
        calc_DAQ_rate_every_N_iter      = 5,
        DEBUG                           = True)
    qdevio.start_worker_DAQ()
    
    # Simulate device runtime
    time.sleep(.1)  # Worker starts suspended
    qdevio.worker_DAQ.schedule_suspend(False)
    time.sleep(.3)  # running
    qdevio.worker_DAQ.schedule_suspend(True)
    time.sleep(.1)  # suspended
    qdevio.worker_DAQ.schedule_suspend(False)
    time.sleep(.3)  # running
    
    print("About to quit")
    app.processEvents()
    assert qdevio.quit_worker_DAQ() == True
    app.quit()
    
    assert dev.counter == 6
    


def test_Worker_DAQ__SINGLE_SHOT_WAKE_UP():
    print("\nTEST Worker_DAQ SINGLE_SHOT_WAKE_UP")
    print("-----------------------------------")
    app = create_QApplication()
    
    # Simulate a device
    dev = FakeDevice()
    def DAQ_function():
        if dev.is_alive:
            dev.counter += 1
            print(dev.counter)
        return dev.is_alive        
    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    qdevio.attach_device(dev)
    
    # Worker_DAQ in mode SINGLE_SHOT_WAKE_UP
    qdevio.create_worker_DAQ(
        DAQ_trigger_by                  = DvG_QDeviceIO.DAQ_trigger.SINGLE_SHOT_WAKE_UP,
        DAQ_function_to_run_each_update = DAQ_function,
        DAQ_critical_not_alive_count    = 1,
        calc_DAQ_rate_every_N_iter      = 5,
        DEBUG                           = True)
    qdevio.start_worker_DAQ()
    
    # Simulate device runtime
    qdevio.worker_DAQ.wake_up()
    time.sleep(.1)
    qdevio.worker_DAQ.wake_up()
    time.sleep(.1)
    qdevio.worker_DAQ.wake_up()
    time.sleep(.1)
    
    print("About to quit")
    app.processEvents()
    assert qdevio.quit_worker_DAQ() == True
    app.quit()
    
    assert dev.counter == 3

    

def test_Worker_send():
    print("\nTEST Worker_send")
    print("----------------")
    app = create_QApplication()
    
    # Simulate a device
    dev = FakeDevice()
    #def alt_process_jobs_function(self, func, args):        
    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    qdevio.attach_device(dev)
    
    qdevio.create_worker_send(DEBUG=True)
    qdevio.start_worker_send()
    
    # Simulate device runtime
    qdevio.worker_send.add_to_queue(dev.fake_query)
    time.sleep(0.1)
    qdevio.worker_send.process_queue()
    time.sleep(0.1)
    qdevio.worker_send.queued_instruction(dev.fake_query)
    time.sleep(0.1)
    qdevio.worker_send.add_to_queue(dev.fake_query)
    time.sleep(0.1)
    qdevio.worker_send.process_queue()
    time.sleep(0.1)
    
    sys.stdout.flush()
    print("About to quit")
    app.processEvents()
    assert qdevio.quit_worker_send() == True
    app.quit()
    
    assert dev.counter == 3
    
    
    
if __name__ == "__main__":
    test_Worker_DAQ__INTERNAL_TIMER()
    test_Worker_DAQ__CONTINUOUS()
    test_Worker_DAQ__SINGLE_SHOT_WAKE_UP()
    test_Worker_send()