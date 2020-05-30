import sys
import time
from PyQt5 import QtCore, QtWidgets
import DvG_QDeviceIO
from DvG_debug_functions import dprint

# TODO: test pyqt_signals coming from QDeviceIO
# See test_Worker_DAQ__midway_dead_device()


"""
DAQ_trigger.INTERNAL_TIMER
    I/O device slaved to an external timer originating from Worker_DAQ

DAQ_trigger.SINGLE_SHOT_WAKE_UP
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

class FakeDevice():
    def __init__(self, name="FakeDev"):
        # Required members
        self.name = name
        self.mutex = QtCore.QMutex()
        self.is_alive = True
        
        # Member for testing
        self.count_commands = 0
        self.count_replies  = 0
        
    def _send(self, data_to_be_send):
        if self.is_alive:
            # Simulate successful device output
            self.count_replies += 1
            dprint(data_to_be_send)
            return data_to_be_send
        else:
            # Simulate device failure
            time.sleep(.1)
            dprint("FAKE DEVICE I/O ERROR")
            return None
    
    def fake_query(self):
        self.count_commands += 1
        return self._send("device reply")
    
    def fake_command_with_argument(self, val):
        self.count_commands += 1


    
def create_QApplication():
    QtCore.QThread.currentThread().setObjectName('MAIN')    # For DEBUG info
    app = 0     # Work-around for kernel crash when using Spyder IDE
    app = QtWidgets.QApplication(sys.argv)
    return app
    


def test_Worker_DAQ__INTERNAL_TIMER(start_alive=True):
    print("\nTEST Worker_DAQ INTERNAL_TIMER")
    if not start_alive: print("start dead")
    print("-" * 30)
    app = create_QApplication()
    
    # Simulate a device
    dev = FakeDevice()
    dev.is_alive = start_alive
    
    def DAQ_function():
        # Must return True when successful, False otherwise
        reply = dev.fake_query()
        return reply == "device reply"
    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True
    
    # Worker_DAQ in mode INTERNAL TIMER
    qdevio.create_worker_DAQ(
        DAQ_trigger_by                  = DvG_QDeviceIO.DAQ_trigger.INTERNAL_TIMER,
        DAQ_function_to_run_each_update = DAQ_function,
        DAQ_update_interval_ms          = 100,
        DAQ_timer_type                  = QtCore.Qt.CoarseTimer,
        DAQ_critical_not_alive_count    = 1,
        calc_DAQ_rate_every_N_iter      = 5,
        DEBUG                           = True)
    
    assert qdevio.start_worker_DAQ() == start_alive
    
    # Simulate device runtime
    time.sleep(.35)
    
    dprint("About to quit")
    app.processEvents()
    assert qdevio.quit_all_workers() == True
    app.quit()
    
    if start_alive:
        assert dev.count_commands == 3
        assert dev.count_replies  == 3
    
    
    
def test_Worker_DAQ__INTERNAL_TIMER__start_dead():
    test_Worker_DAQ__INTERNAL_TIMER(start_alive=False)
    

    

def test_Worker_DAQ__SINGLE_SHOT_WAKE_UP(start_alive=True):
    print("\nTEST Worker_DAQ SINGLE_SHOT_WAKE_UP")
    if not start_alive: print("start dead")
    print("-" * 30)
    app = create_QApplication()
    
    # Simulate a device
    dev = FakeDevice()
    dev.is_alive = start_alive
    
    def DAQ_function():
        # Must return True when successful, False otherwise
        reply = dev.fake_query()
        return reply == "device reply"
    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True
    
    # Worker_DAQ in mode SINGLE_SHOT_WAKE_UP
    qdevio.create_worker_DAQ(
        DAQ_trigger_by                  = DvG_QDeviceIO.DAQ_trigger.SINGLE_SHOT_WAKE_UP,
        DAQ_function_to_run_each_update = DAQ_function,
        DAQ_critical_not_alive_count    = 1,
        calc_DAQ_rate_every_N_iter      = 5,
        DEBUG                           = True)
    
    assert qdevio.start_worker_DAQ() == start_alive
    
    # Simulate device runtime
    qdevio.worker_DAQ.wake_up()
    time.sleep(.1)
    qdevio.worker_DAQ.wake_up()
    time.sleep(.1)
    qdevio.worker_DAQ.wake_up()
    time.sleep(.1)
    
    dprint("About to quit")
    app.processEvents()
    assert qdevio.quit_all_workers() == True
    app.quit()
    
    if start_alive:
        assert dev.count_commands == 3
        assert dev.count_replies  == 3

    

def test_Worker_DAQ__SINGLE_SHOT_WAKE_UP__start_dead():
    test_Worker_DAQ__SINGLE_SHOT_WAKE_UP(start_alive=False)
    
    

def test_Worker_DAQ__CONTINUOUS(start_alive=True):
    print("\nTEST Worker_DAQ CONTINUOUS")
    if not start_alive: print("start dead")
    print("-" * 30)
    app = create_QApplication()
    
    # Simulate a device
    dev = FakeDevice()
    dev.is_alive = start_alive
    
    def DAQ_function():
        # Must return True when successful, False otherwise
        time.sleep(.1)
        reply = dev.fake_query()
        return reply == "device reply"
    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True
    
    # Worker_DAQ in mode CONTINUOUS
    qdevio.create_worker_DAQ(
        DAQ_trigger_by                  = DvG_QDeviceIO.DAQ_trigger.CONTINUOUS,
        DAQ_function_to_run_each_update = DAQ_function,
        DAQ_critical_not_alive_count    = 1,
        calc_DAQ_rate_every_N_iter      = 5,
        DEBUG                           = True)
    
    assert qdevio.start_worker_DAQ() == start_alive
    
    # Simulate device runtime
    time.sleep(.1)  # Worker starts suspended
    qdevio.worker_DAQ.schedule_suspend(False)
    time.sleep(.3)  # running
    qdevio.worker_DAQ.schedule_suspend(True)
    time.sleep(.1)  # suspended
    qdevio.worker_DAQ.schedule_suspend(False)
    time.sleep(.3)  # running
    
    dprint("About to quit")
    app.processEvents()
    assert qdevio.quit_all_workers() == True
    app.quit()
    
    if start_alive:
        assert dev.count_commands == 6
        assert dev.count_replies  == 6
        


def test_Worker_DAQ__CONTINUOUS__start_dead():
    test_Worker_DAQ__CONTINUOUS(start_alive=False)
    
    
    
def test_Worker_send(start_alive=True):
    print("\nTEST Worker_send")
    if not start_alive: print("start dead")
    print("-" * 30)
    app = create_QApplication()
    
    # Simulate a device
    dev = FakeDevice()
    dev.is_alive = start_alive
    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True
    
    qdevio.create_worker_send(DEBUG=True)
    
    assert qdevio.start_worker_send() == start_alive
    
    # Simulate device runtime
    qdevio.worker_send.add_to_queue(dev.fake_query)
    time.sleep(0.1)
    qdevio.worker_send.process_queue()
    time.sleep(0.1)
    qdevio.worker_send.queued_instruction(dev.fake_query)
    time.sleep(0.1)
    qdevio.worker_send.add_to_queue(dev.fake_command_with_argument, 0)
    time.sleep(0.1)
    qdevio.worker_send.add_to_queue(dev.fake_command_with_argument, 0)
    time.sleep(0.1)
    qdevio.worker_send.add_to_queue(dev.fake_command_with_argument, 0)
    time.sleep(0.1)
    qdevio.worker_send.process_queue()
    time.sleep(0.1)
    qdevio.worker_send.queued_instruction("trigger_illegal_function_call_error")
    time.sleep(0.1)
    
    dprint("About to quit")
    app.processEvents()
    assert qdevio.quit_all_workers() == True
    app.quit()
    
    if start_alive:
        assert dev.count_commands == 5
        assert dev.count_replies  == 2
        
        
        
def test_Worker_send__start_dead():
    test_Worker_send(start_alive=False)



def test_Worker_send__alt_jobs():
    print("\nTEST Worker_send")
    print("alternative jobs")
    print("-" * 30)
    app = create_QApplication()
    
    # Simulate a device
    dev = FakeDevice()
    
    def my_alt_process_jobs_function(func, args):
        if func == "special command":
            dev.fake_query()
        else:
            # Default job handling where, e.g.
            # func = self.dev.write
            # args = ("toggle LED",)
            func(*args)
    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True
    
    qdevio.create_worker_send(
        alt_process_jobs_function=my_alt_process_jobs_function,
        DEBUG=True)
    
    assert qdevio.start_worker_send() == True
    
    # Simulate device runtime
    qdevio.worker_send.queued_instruction(dev.fake_query)
    time.sleep(0.1)
    qdevio.worker_send.queued_instruction("special command")
    time.sleep(0.1)
    qdevio.worker_send.queued_instruction(dev.fake_command_with_argument, 0)
    time.sleep(0.1)
    
    dprint("About to quit")
    app.processEvents()
    assert qdevio.quit_all_workers() == True
    app.quit()
    
    assert dev.count_commands == 3
    assert dev.count_replies  == 2
    
    
    
def test_Worker_DAQ__start_worker_without_create():
    print("\nTEST Worker_DAQ")
    print("start worker without create")
    print("-" * 30)
    
    dev = FakeDevice()    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True
    assert qdevio.start_worker_DAQ() == False
    assert qdevio.quit_all_workers() == True


    
def test_Worker_send__start_worker_without_create():
    print("\nTEST Worker_send")
    print("start worker without create")
    print("-" * 30)
    
    dev = FakeDevice()        
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True
    assert qdevio.start_worker_send() == False
    assert qdevio.quit_all_workers() == True
    
    
    
def test_attach_device_twice():
    print("\nTEST attach device twice")
    print("-" * 30)
    
    dev = FakeDevice()    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True
    assert qdevio.attach_device(dev) == False
    


def test_no_device_attached():
    print("\nTEST no device attached")
    print("-" * 30)
    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    qdevio.create_worker_DAQ()
    assert qdevio.start_worker_DAQ() == False
    assert qdevio.quit_all_workers() == True

    
    
def test_Worker_DAQ__rate():
    print("\nTEST Worker_DAQ INTERNAL_TIMER")
    print("DAQ rate")
    print("-" * 30)
    app = create_QApplication()
    
    # Simulate a device
    dev = FakeDevice()
    
    def DAQ_function():
        dprint(qdevio.obtained_DAQ_update_interval_ms)
        dprint(qdevio.obtained_DAQ_rate_Hz)
        return True
    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True
    
    # Worker_DAQ in mode INTERNAL TIMER
    qdevio.create_worker_DAQ(
        DAQ_trigger_by                  = DvG_QDeviceIO.DAQ_trigger.INTERNAL_TIMER,
        DAQ_function_to_run_each_update = DAQ_function,
        DAQ_update_interval_ms          = 20,
        DAQ_timer_type                  = QtCore.Qt.PreciseTimer,
        DAQ_critical_not_alive_count    = 1,
        calc_DAQ_rate_every_N_iter      = 25,
        DEBUG                           = True)
    
    print(qdevio.worker_DAQ.calc_DAQ_rate_every_N_iter)
    assert qdevio.start_worker_DAQ() == True
    
    # Simulate device runtime
    time.sleep(1.02)
    
    dprint("About to quit")
    app.processEvents()
    assert qdevio.quit_all_workers() == True
    app.quit()
    
    assert (
        qdevio.obtained_DAQ_update_interval_ms >= 19 &
        qdevio.obtained_DAQ_update_interval_ms <= 21)
    assert round(qdevio.obtained_DAQ_rate_Hz) == 50
    
    
    
def test_Worker_DAQ__midway_dead_device():
    print("\nTEST Worker_DAQ INTERNAL_TIMER")
    print("midway dead device")
    print("-" * 30)
    app = create_QApplication()
    
    # Simulate a device
    dev = FakeDevice()
    
    def DAQ_function():
        if qdevio.DAQ_update_counter == 30:
            dev.is_alive = False
        reply = dev.fake_query()
        dprint(qdevio.obtained_DAQ_update_interval_ms)
        dprint(qdevio.obtained_DAQ_rate_Hz)
        return reply == "device reply"
    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True
    
    # Worker_DAQ in mode INTERNAL TIMER
    qdevio.create_worker_DAQ(
        DAQ_trigger_by                  = DvG_QDeviceIO.DAQ_trigger.INTERNAL_TIMER,
        DAQ_function_to_run_each_update = DAQ_function,
        DAQ_update_interval_ms          = 20,
        DAQ_timer_type                  = QtCore.Qt.PreciseTimer,
        DAQ_critical_not_alive_count    = 3,
        calc_DAQ_rate_every_N_iter      = 20,
        DEBUG                           = True)
    
    global go
    go = True
    
    @QtCore.pyqtSlot()
    def process_connection_lost():
        dprint("---> Received signal: connection_lost")
        global go
        go = False

    qdevio.signal_connection_lost.connect(process_connection_lost)
    
    assert qdevio.start_worker_DAQ() == True
    
    # Simulate device runtime
    while go:
        app.processEvents()
        
    dprint("About to quit")
    app.processEvents()
    assert qdevio.quit_all_workers() == True
    app.quit()
    
    
    
if __name__ == "__main__":
    #"""
    test_Worker_DAQ__INTERNAL_TIMER()
    test_Worker_DAQ__INTERNAL_TIMER__start_dead()
    test_Worker_DAQ__SINGLE_SHOT_WAKE_UP()
    test_Worker_DAQ__SINGLE_SHOT_WAKE_UP__start_dead()
    test_Worker_DAQ__CONTINUOUS()
    test_Worker_DAQ__CONTINUOUS__start_dead()
    test_Worker_send()
    test_Worker_send__start_dead()
    test_Worker_send__alt_jobs()
    test_Worker_DAQ__start_worker_without_create()
    test_Worker_send__start_worker_without_create()
    test_attach_device_twice()
    test_no_device_attached()
    test_Worker_DAQ__rate()
    test_Worker_DAQ__midway_dead_device()
    #"""
    #test_Worker_send()