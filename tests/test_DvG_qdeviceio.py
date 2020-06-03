import sys
import time
from PyQt5 import QtCore
import DvG_QDeviceIO
from DvG_debug_functions import dprint, ANSI

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
            dprint("%f SIMULATED I/O ERROR" % time.perf_counter())
            return "SIMULATED I/O ERROR"
    
    def fake_query(self):
        self.count_commands += 1
        return self._send("%f device replied" % time.perf_counter())
    
    def fake_command_with_argument(self, val):
        dprint("%f device received command" % time.perf_counter())
        self.count_commands += 1


    
def create_QApplication():
    QtCore.QThread.currentThread().setObjectName('MAIN')    # For DEBUG info
    app = 0     # Work-around for kernel crash when using Spyder IDE
    # QtWidgets are not needed for pytest and will fail standard Travis test
    #app = QtWidgets.QApplication(sys.argv)
    app = QtCore.QCoreApplication(sys.argv) # Use QCoreApplication instead
    return app
    


def test_Worker_DAQ__INTERNAL_TIMER(start_alive=True):
    dprint("\nTEST Worker_DAQ INTERNAL_TIMER", ANSI.PURPLE)
    if not start_alive: dprint("start dead", ANSI.PURPLE)
    dprint("-" * 50, ANSI.PURPLE)
    app = create_QApplication()
    
    # Simulate a device
    dev = FakeDevice()
    dev.is_alive = start_alive
    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True
    
    def DAQ_function():
        # Must return True when successful, False otherwise
        reply = dev.fake_query()
        return reply[-14:] == "device replied"
    
    global pytest_counter_signal_DAQ_updated 
    pytest_counter_signal_DAQ_updated = 0
    @QtCore.pyqtSlot()
    def process_DAQ_updated():
        # In production code, your GUI update routine would go here
        dprint("%f ---> Received signal: DAQ_updated" % time.perf_counter())
        global pytest_counter_signal_DAQ_updated 
        pytest_counter_signal_DAQ_updated += 1

    qdevio.signal_DAQ_updated.connect(process_DAQ_updated)
    
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
    
    # Give time to enter '_do_work'. TODO: Should be implemented by a mechanism inside DvG_QDeviceIO
    start_time = time.perf_counter()
    while time.perf_counter() - start_time < .1:
        app.processEvents()
        time.sleep(.001)    # Do not hog the CPU
    
    # Simulate device runtime
    start_time = time.perf_counter()
    while time.perf_counter() - start_time < 1:
        app.processEvents()
        if dev.count_commands == 3:
            break
        time.sleep(.001)    # Do not hog the CPU
    
    dprint("%f About to quit" % time.perf_counter())
    app.processEvents()
    assert qdevio.quit_all_workers() == True
    app.quit()
    
    if start_alive:
        assert dev.count_commands >= 3
        assert dev.count_replies  >= 3
        assert pytest_counter_signal_DAQ_updated >= 2 # Third signal is not always received before thread is quit
    
    
    
def test_Worker_DAQ__INTERNAL_TIMER__start_dead():
    test_Worker_DAQ__INTERNAL_TIMER(start_alive=False)
    

    

def test_Worker_DAQ__SINGLE_SHOT_WAKE_UP(start_alive=True):
    dprint("\nTEST Worker_DAQ SINGLE_SHOT_WAKE_UP", ANSI.PURPLE)
    if not start_alive: dprint("start dead", ANSI.PURPLE)
    dprint("-" * 50, ANSI.PURPLE)
    app = create_QApplication()
    
    # Simulate a device
    dev = FakeDevice()
    dev.is_alive = start_alive
    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True
    
    def DAQ_function():
        # Must return True when successful, False otherwise
        reply = dev.fake_query()
        return reply[-14:] == "device replied"
    
    global pytest_counter_signal_DAQ_updated 
    pytest_counter_signal_DAQ_updated = 0
    @QtCore.pyqtSlot()
    def process_DAQ_updated():
        # In production code, your GUI update routine would go here
        dprint("%f ---> Received signal: DAQ_updated" % time.perf_counter())
        global pytest_counter_signal_DAQ_updated 
        pytest_counter_signal_DAQ_updated += 1
    
    qdevio.signal_DAQ_updated.connect(process_DAQ_updated)
    
    # Worker_DAQ in mode SINGLE_SHOT_WAKE_UP
    qdevio.create_worker_DAQ(
        DAQ_trigger_by                  = DvG_QDeviceIO.DAQ_trigger.SINGLE_SHOT_WAKE_UP,
        DAQ_function_to_run_each_update = DAQ_function,
        DAQ_critical_not_alive_count    = 1,
        calc_DAQ_rate_every_N_iter      = 5,
        DEBUG                           = True)
    
    assert qdevio.start_worker_DAQ() == start_alive
    
    # Give time to enter '_do_work'. TODO: Should be implemented by a mechanism inside DvG_QDeviceIO
    start_time = time.perf_counter()
    while time.perf_counter() - start_time < .1:
        app.processEvents()
        time.sleep(.001)    # Do not hog the CPU
    
    # Simulate device runtime
    start_time = time.perf_counter()
    QtCore.QTimer.singleShot(000, lambda: qdevio.worker_DAQ.wake_up())
    QtCore.QTimer.singleShot(300, lambda: qdevio.worker_DAQ.wake_up())
    QtCore.QTimer.singleShot(600, lambda: qdevio.worker_DAQ.wake_up())
    while time.perf_counter() - start_time < 1:
        app.processEvents()
        time.sleep(.001)    # Do not hog the CPU

    dprint("%f About to quit" % time.perf_counter())
    app.processEvents()
    assert qdevio.quit_all_workers() == True
    app.quit()
    
    if start_alive:
        assert dev.count_commands == 3
        assert dev.count_replies  == 3
        assert pytest_counter_signal_DAQ_updated == 3
    

def test_Worker_DAQ__SINGLE_SHOT_WAKE_UP__start_dead():
    test_Worker_DAQ__SINGLE_SHOT_WAKE_UP(start_alive=False)
    
    

def test_Worker_DAQ__CONTINUOUS(start_alive=True):
    dprint("\nTEST Worker_DAQ CONTINUOUS", ANSI.PURPLE)
    if not start_alive: dprint("start dead", ANSI.PURPLE)
    dprint("-" * 50, ANSI.PURPLE)
    app = create_QApplication()
    
    # Simulate a device
    dev = FakeDevice()
    dev.is_alive = start_alive
    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True
    
    def DAQ_function():
        # Must return True when successful, False otherwise
        time.sleep(.1)
        reply = dev.fake_query()
        return reply[-14:] == "device replied"
    
    global pytest_counter_signal_DAQ_paused
    pytest_counter_signal_DAQ_paused = 0
    @QtCore.pyqtSlot()
    def process_DAQ_paused():
        # In production code, your GUI update routine would go here
        dprint("%f ---> Received signal: DAQ_paused" % time.perf_counter())
        global pytest_counter_signal_DAQ_paused 
        pytest_counter_signal_DAQ_paused += 1

    qdevio.signal_DAQ_paused.connect(process_DAQ_paused)
    
    # Worker_DAQ in mode CONTINUOUS
    qdevio.create_worker_DAQ(
        DAQ_trigger_by                  = DvG_QDeviceIO.DAQ_trigger.CONTINUOUS,
        DAQ_function_to_run_each_update = DAQ_function,
        DAQ_critical_not_alive_count    = 1,
        calc_DAQ_rate_every_N_iter      = 5,
        DEBUG                           = True)
    
    assert qdevio.start_worker_DAQ() == start_alive
    
    # Give time to enter '_do_work'. TODO: Should be implemented by a mechanism inside DvG_QDeviceIO
    start_time = time.perf_counter()
    while time.perf_counter() - start_time < .1:
        app.processEvents()
        time.sleep(.001)    # Do not hog the CPU
    
    # Simulate device runtime
    start_time = time.perf_counter()
    QtCore.QTimer.singleShot(000, lambda: qdevio.worker_DAQ.unpause())
    QtCore.QTimer.singleShot(300, lambda: qdevio.worker_DAQ.pause())
    QtCore.QTimer.singleShot(600, lambda: qdevio.worker_DAQ.unpause())
    while time.perf_counter() - start_time < 1:
        app.processEvents()
        if dev.count_commands == 6:
            break
        time.sleep(.001)    # Do not hog the CPU
    
    dprint("%f About to quit" % time.perf_counter())
    app.processEvents()
    assert qdevio.quit_all_workers() == True
    app.quit()
    
    if start_alive:
        assert dev.count_commands >= 6
        assert dev.count_replies  >= 6
        assert pytest_counter_signal_DAQ_paused == 2
        


def test_Worker_DAQ__CONTINUOUS__start_dead():
    test_Worker_DAQ__CONTINUOUS(start_alive=False)
    
    
    
def test_Worker_send(start_alive=True):
    dprint("\nTEST Worker_send", ANSI.PURPLE)
    if not start_alive: dprint("start dead", ANSI.PURPLE)
    dprint("-" * 50, ANSI.PURPLE)
    app = create_QApplication()
    
    # Simulate a device
    dev = FakeDevice()
    dev.is_alive = start_alive
    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True
    
    qdevio.create_worker_send(DEBUG=True)
    
    assert qdevio.start_worker_send() == start_alive
    
    # Give time to enter '_do_work'. TODO: Should be implemented by a mechanism inside DvG_QDeviceIO
    start_time = time.perf_counter()
    while time.perf_counter() - start_time < .1:
        app.processEvents()
        time.sleep(.001)    # Do not hog the CPU
    
    # Simulate device runtime
    start_time = time.perf_counter()
    QtCore.QTimer.singleShot(000, lambda: qdevio.worker_send.add_to_queue(dev.fake_query))
    QtCore.QTimer.singleShot(100, lambda: qdevio.worker_send.process_queue())
    QtCore.QTimer.singleShot(200, lambda: qdevio.worker_send.queued_instruction(dev.fake_query))
    QtCore.QTimer.singleShot(300, lambda: qdevio.worker_send.add_to_queue(dev.fake_command_with_argument, 0))
    QtCore.QTimer.singleShot(400, lambda: qdevio.worker_send.add_to_queue(dev.fake_command_with_argument, 0))
    QtCore.QTimer.singleShot(500, lambda: qdevio.worker_send.add_to_queue(dev.fake_command_with_argument, 0))
    QtCore.QTimer.singleShot(600, lambda: qdevio.worker_send.process_queue())
    QtCore.QTimer.singleShot(700, lambda: qdevio.worker_send.queued_instruction("trigger_illegal_function_call_error"))
    while time.perf_counter() - start_time < 1:
        app.processEvents()
        time.sleep(.001)    # Do not hog the CPU
    
    dprint("%f About to quit" % time.perf_counter())
    app.processEvents()
    assert qdevio.quit_all_workers() == True
    app.quit()
    
    if start_alive:
        assert dev.count_commands == 5
        assert dev.count_replies  == 2
        
        
        
def test_Worker_send__start_dead():
    test_Worker_send(start_alive=False)



def test_Worker_send__alt_jobs():
    dprint("\nTEST Worker_send", ANSI.PURPLE)
    dprint("alternative jobs", ANSI.PURPLE)
    dprint("-" * 50, ANSI.PURPLE)
    app = create_QApplication()
    
    # Simulate a device
    dev = FakeDevice()
    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True
    
    def my_alt_process_jobs_function(func, args):
        if func == "special command":
            dev.fake_query()
        else:
            # Default job handling where, e.g.
            # func = self.dev.write
            # args = ("toggle LED",)
            func(*args)
    
    qdevio.create_worker_send(
        alt_process_jobs_function=my_alt_process_jobs_function,
        DEBUG=True)
    
    assert qdevio.start_worker_send() == True
    
    # Give time to enter '_do_work'. TODO: Should be implemented by a mechanism inside DvG_QDeviceIO
    start_time = time.perf_counter()
    while time.perf_counter() - start_time < .1:
        app.processEvents()
        time.sleep(.001)    # Do not hog the CPU
    
    # Simulate device runtime
    start_time = time.perf_counter()
    QtCore.QTimer.singleShot(000, lambda: qdevio.worker_send.queued_instruction(dev.fake_query))
    QtCore.QTimer.singleShot(100, lambda: qdevio.worker_send.queued_instruction("special command"))
    QtCore.QTimer.singleShot(200, lambda: qdevio.worker_send.queued_instruction(dev.fake_command_with_argument, 0))
    while time.perf_counter() - start_time < .5:
        app.processEvents()
        time.sleep(.001)    # Do not hog the CPU
    
    dprint("%f About to quit" % time.perf_counter())
    app.processEvents()
    assert qdevio.quit_all_workers() == True
    app.quit()
    
    assert dev.count_commands == 3
    assert dev.count_replies  == 2
    
    
    
def test_Worker_DAQ__start_without_create():
    dprint("\nTEST Worker_DAQ", ANSI.PURPLE)
    dprint("start worker without create", ANSI.PURPLE)
    dprint("-" * 50, ANSI.PURPLE)
    
    dev = FakeDevice()    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True
    assert qdevio.start_worker_DAQ() == False
    assert qdevio.quit_all_workers() == True


    
def test_Worker_send__start_without_create():
    dprint("\nTEST Worker_send", ANSI.PURPLE)
    dprint("start worker without create", ANSI.PURPLE)
    dprint("-" * 50, ANSI.PURPLE)
    
    dev = FakeDevice()        
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True
    assert qdevio.start_worker_send() == False
    assert qdevio.quit_all_workers() == True
    
    
    
def test_attach_device_twice():
    dprint("\nTEST attach device twice", ANSI.PURPLE)
    dprint("-" * 50, ANSI.PURPLE)
    
    dev = FakeDevice()    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True
    assert qdevio.attach_device(dev) == False
    


def test_no_device_attached():
    dprint("\nTEST no device attached", ANSI.PURPLE)
    dprint("-" * 50, ANSI.PURPLE)
    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    qdevio.create_worker_DAQ()
    assert qdevio.start_worker_DAQ() == False
    assert qdevio.quit_all_workers() == True

    
    
def test_Worker_DAQ__rate():
    dprint("\nTEST Worker_DAQ INTERNAL_TIMER", ANSI.PURPLE)
    dprint("DAQ rate", ANSI.PURPLE)
    dprint("-" * 50, ANSI.PURPLE)
    app = create_QApplication()
    
    # Simulate a device
    dev = FakeDevice()
    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True
    
    def DAQ_function():
        dprint(qdevio.obtained_DAQ_update_interval_ms)
        dprint(qdevio.obtained_DAQ_rate_Hz)
        return True
    
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
    
    # Give time to enter '_do_work'. TODO: Should be implemented by a mechanism inside DvG_QDeviceIO
    start_time = time.perf_counter()
    while time.perf_counter() - start_time < .1:
        app.processEvents()
        time.sleep(.001)    # Do not hog the CPU
    
    # Simulate device runtime
    start_time = time.perf_counter()
    while time.perf_counter() - start_time < 1.02:
        app.processEvents()
        time.sleep(.001)    # Do not hog the CPU
    
    dprint("%f About to quit" % time.perf_counter())
    app.processEvents()
    assert qdevio.quit_all_workers() == True
    app.quit()
    
    assert (
        qdevio.obtained_DAQ_update_interval_ms >= 19 &
        qdevio.obtained_DAQ_update_interval_ms <= 21)
    assert round(qdevio.obtained_DAQ_rate_Hz) == 50
    
    
    
def test_Worker_DAQ__lose_connection():
    dprint("\nTEST Worker_DAQ INTERNAL_TIMER", ANSI.PURPLE)
    dprint("lose connection", ANSI.PURPLE)
    dprint("-" * 50, ANSI.PURPLE)
    app = create_QApplication()
    
    # Simulate a device
    dev = FakeDevice()
    
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True
    
    def DAQ_function():
        if qdevio.DAQ_update_counter == 30:
            dev.is_alive = False
        reply = dev.fake_query()
        dprint(qdevio.obtained_DAQ_update_interval_ms)
        dprint(qdevio.obtained_DAQ_rate_Hz)
        return reply[-14:] == "device replied"
    
    # Worker_DAQ in mode INTERNAL TIMER
    qdevio.create_worker_DAQ(
        DAQ_trigger_by                  = DvG_QDeviceIO.DAQ_trigger.INTERNAL_TIMER,
        DAQ_function_to_run_each_update = DAQ_function,
        DAQ_update_interval_ms          = 20,
        DAQ_timer_type                  = QtCore.Qt.PreciseTimer,
        DAQ_critical_not_alive_count    = 3,
        calc_DAQ_rate_every_N_iter      = 20,
        DEBUG                           = True)
    
    # NOTE: The global 'go' mechanism used here is a quick and dirty way to
    # pytest. In production, it should be implemented by an boolean external
    # class member.
    global go
    go = True
    
    @QtCore.pyqtSlot()
    def process_connection_lost():
        dprint("%f ---> Received signal: connection_lost" % time.perf_counter())
        global go
        go = False

    qdevio.signal_connection_lost.connect(process_connection_lost)
    
    assert qdevio.start_worker_DAQ() == True
    
    # Give time to enter '_do_work'. TODO: Should be implemented by a mechanism inside DvG_QDeviceIO
    start_time = time.perf_counter()
    while time.perf_counter() - start_time < .1:
        app.processEvents()
        time.sleep(.001)    # Do not hog the CPU
    
    # Simulate device runtime
    while go:
        app.processEvents()
        time.sleep(.001)    # Do not hog the CPU
        
    dprint("%f About to quit" % time.perf_counter())
    app.processEvents()
    assert qdevio.quit_all_workers() == True
    app.quit()
    
    
    
if __name__ == "__main__":
    ALL = False
    if ALL:
        test_Worker_DAQ__INTERNAL_TIMER()
        test_Worker_DAQ__INTERNAL_TIMER__start_dead()
        test_Worker_DAQ__SINGLE_SHOT_WAKE_UP()
        test_Worker_DAQ__SINGLE_SHOT_WAKE_UP__start_dead()
        test_Worker_DAQ__CONTINUOUS()
        test_Worker_DAQ__CONTINUOUS__start_dead()
        test_Worker_send()
        test_Worker_send__start_dead()
        test_Worker_send__alt_jobs()
        test_Worker_DAQ__start_without_create()
        test_Worker_send__start_without_create()
        test_attach_device_twice()
        test_no_device_attached()
        test_Worker_DAQ__rate()
        test_Worker_DAQ__lose_connection()
    else:
        test_Worker_DAQ__INTERNAL_TIMER()
        test_Worker_DAQ__INTERNAL_TIMER__start_dead()
        #test_Worker_DAQ__SINGLE_SHOT_WAKE_UP()
        #test_Worker_DAQ__CONTINUOUS()
        #test_Worker_send__alt_jobs()