import sys
import time
from PyQt5 import QtCore
import DvG_QDeviceIO
from DvG_debug_functions import dprint, tprint, ANSI

# Show extra debug info in terminal?
DEBUG = True

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
            qdevio.wake_up()
            
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


class FakeDevice:
    def __init__(self, name="FakeDev"):
        # Required members
        self.name = name
        self.mutex = QtCore.QMutex()
        self.is_alive = True

        # Member for testing
        self.count_commands = 0
        self.count_replies = 0

    def _send(self, data_to_be_send):
        if self.is_alive:
            # Simulate successful device output
            self.count_replies += 1
            tprint(data_to_be_send)
            return data_to_be_send
        else:
            # Simulate device failure
            time.sleep(0.1)
            tprint("SIMULATED I/O ERROR")
            return "SIMULATED I/O ERROR"

    def fake_query(self):
        self.count_commands += 1
        return self._send("device replied")

    def fake_command_with_argument(self, val):
        tprint("device received command")
        self.count_commands += 1


def create_QApplication():
    QtCore.QThread.currentThread().setObjectName("MAIN")  # For DEBUG info
    app = 0  # Work-around for kernel crash when using Spyder IDE
    # QtWidgets are not needed for pytest and will fail standard Travis test
    # app = QtWidgets.QApplication(sys.argv)
    app = QtCore.QCoreApplication(sys.argv)  # Use QCoreApplication instead
    return app


def print_title(title):
    dprint("\n%s" % title, ANSI.PURPLE)
    dprint("-" * 50, ANSI.PURPLE)


def test_Worker_DAQ___INTERNAL_TIMER(start_alive=True):
    print_title(
        "Worker_DAQ - INTERNAL_TIMER" + ("" if start_alive else " - start dead")
    )
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

    global signal_counter
    signal_counter = 0

    @QtCore.pyqtSlot()
    def process_DAQ_updated():
        # In production code, your GUI update routine would go here
        tprint("---> Received signal: DAQ_updated")
        global signal_counter
        signal_counter += 1

    qdevio.signal_DAQ_updated.connect(process_DAQ_updated)

    # fmt: off
    # Worker_DAQ in mode INTERNAL TIMER
    qdevio.create_worker_DAQ(
        DAQ_trigger                     = DvG_QDeviceIO.DAQ_trigger.INTERNAL_TIMER,
        DAQ_function                    = DAQ_function,
        DAQ_interval_ms                 = 100,
        DAQ_timer_type                  = QtCore.Qt.CoarseTimer,
        critical_not_alive_count        = 10,
        calc_DAQ_rate_every_N_iter      = 5,
        DEBUG                           = DEBUG)
    # fmt: on

    assert qdevio.start() == start_alive

    # Simulate device runtime
    start_time = time.perf_counter()
    while time.perf_counter() - start_time < 1:
        app.processEvents()
        if dev.count_commands == 3:
            break
        time.sleep(0.001)  # Do not hog the CPU

    tprint("About to quit")
    app.processEvents()
    assert qdevio.quit() == True
    app.quit()

    if start_alive:
        assert dev.count_commands >= 3
        assert dev.count_replies >= 3
        assert (
            signal_counter >= 2
        )  # Third signal is not always received before thread is quit


def test_Worker_DAQ___INTERNAL_TIMER__start_dead():
    test_Worker_DAQ___INTERNAL_TIMER(start_alive=False)


def test_Worker_DAQ___SINGLE_SHOT_WAKE_UP(start_alive=True):
    print_title(
        "Worker_DAQ - SINGLE_SHOT_WAKE_UP"
        + ("" if start_alive else " - start dead")
    )
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

    global signal_counter
    signal_counter = 0

    @QtCore.pyqtSlot()
    def process_DAQ_updated():
        # In production code, your GUI update routine would go here
        tprint("---> Received signal: DAQ_updated")
        global signal_counter
        signal_counter += 1

    qdevio.signal_DAQ_updated.connect(process_DAQ_updated)

    # fmt: off
    # Worker_DAQ in mode SINGLE_SHOT_WAKE_UP
    qdevio.create_worker_DAQ(
        DAQ_trigger                     = DvG_QDeviceIO.DAQ_trigger.SINGLE_SHOT_WAKE_UP,
        DAQ_function                    = DAQ_function,
        critical_not_alive_count        = 1,
        calc_DAQ_rate_every_N_iter      = 5,
        DEBUG                           = DEBUG)
    # fmt: on

    assert qdevio.start() == start_alive

    # Immediately fire a call to test if the worker is ready for it
    qdevio.wake_up_DAQ()

    # Simulate device runtime
    start_time = time.perf_counter()
    QtCore.QTimer.singleShot(300, lambda: qdevio.wake_up_DAQ())
    QtCore.QTimer.singleShot(600, lambda: qdevio.wake_up_DAQ())
    while time.perf_counter() - start_time < 1:
        app.processEvents()
        time.sleep(0.001)  # Do not hog the CPU

    tprint("About to quit")
    app.processEvents()
    assert qdevio.quit() == True
    app.quit()

    if start_alive:
        assert dev.count_commands == 3
        assert dev.count_replies == 3
        assert signal_counter == 3


def test_Worker_DAQ___SINGLE_SHOT_WAKE_UP__start_dead():
    test_Worker_DAQ___SINGLE_SHOT_WAKE_UP(start_alive=False)


def test_Worker_DAQ___CONTINUOUS(start_alive=True):
    print_title(
        "Worker_DAQ - CONTINUOUS" + ("" if start_alive else " - start dead")
    )
    app = create_QApplication()

    # Simulate a device
    dev = FakeDevice()
    dev.is_alive = start_alive

    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True

    def DAQ_function():
        # Must return True when successful, False otherwise
        time.sleep(0.1)  # Simulate blocking processing time on the device
        reply = dev.fake_query()
        return reply[-14:] == "device replied"

    global signal_counter_updated
    signal_counter_updated = 0

    @QtCore.pyqtSlot()
    def process_DAQ_updated():
        # In production code, your GUI update routine would go here
        tprint("---> Received signal: DAQ_updated")
        global signal_counter_updated
        signal_counter_updated += 1

    global signal_counter_paused
    signal_counter_paused = 0

    @QtCore.pyqtSlot()
    def process_DAQ_paused():
        # In production code, your GUI update routine would go here
        tprint("---> Received signal: DAQ_paused")
        global signal_counter_paused
        signal_counter_paused += 1

    qdevio.signal_DAQ_updated.connect(process_DAQ_updated)
    qdevio.signal_DAQ_paused.connect(process_DAQ_paused)

    # fmt: off
    # Worker_DAQ in mode CONTINUOUS
    qdevio.create_worker_DAQ(
        DAQ_trigger                     = DvG_QDeviceIO.DAQ_trigger.CONTINUOUS,
        DAQ_function                    = DAQ_function,
        critical_not_alive_count        = 1,
        calc_DAQ_rate_every_N_iter      = 5,
        DEBUG                           = DEBUG)
    # fmt: on

    assert qdevio.start() == start_alive

    # Immediately fire a call to test if the worker is ready for it
    qdevio.unpause_DAQ()

    # Simulate device runtime
    start_time = time.perf_counter()
    QtCore.QTimer.singleShot(300, lambda: qdevio.pause_DAQ())
    QtCore.QTimer.singleShot(600, lambda: qdevio.unpause_DAQ())
    QtCore.QTimer.singleShot(900, lambda: qdevio.pause_DAQ())
    QtCore.QTimer.singleShot(1200, lambda: qdevio.unpause_DAQ())
    while time.perf_counter() - start_time < 1.6:
        app.processEvents()
        if dev.count_commands == 12:
            break
        time.sleep(0.001)  # Do not hog the CPU

    tprint("About to quit")
    app.processEvents()
    assert qdevio.quit() == True
    app.quit()

    if start_alive:
        assert dev.count_commands >= 10
        assert dev.count_replies >= 10
        assert (
            signal_counter_updated >= 9
        )  # Last signal is not always received before thread is quit
        assert signal_counter_paused == 3


def test_Worker_DAQ___CONTINUOUS__start_dead():
    test_Worker_DAQ___CONTINUOUS(start_alive=False)


def test_Worker_send(start_alive=True):
    print_title("Worker_send" + ("" if start_alive else " - start dead"))
    app = create_QApplication()

    # Simulate a device
    dev = FakeDevice()
    dev.is_alive = start_alive

    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True

    global signal_counter
    signal_counter = 0

    @QtCore.pyqtSlot()
    def process_send_updated():
        # In production code, your GUI update routine would go here
        tprint("---> Received signal: send_updated")
        global signal_counter
        signal_counter += 1

    qdevio.signal_send_updated.connect(process_send_updated)

    qdevio.create_worker_send(DEBUG=DEBUG)

    assert qdevio.start() == start_alive

    # Immediately fire a call to test if the worker is ready for it
    qdevio.add_to_send_queue(dev.fake_query)

    # fmt: off
    # Simulate device runtime
    start_time = time.perf_counter()
    QtCore.QTimer.singleShot(100, lambda: qdevio.process_send_queue())
    QtCore.QTimer.singleShot(200, lambda: qdevio.send(dev.fake_query))
    QtCore.QTimer.singleShot(300, lambda: qdevio.add_to_send_queue(dev.fake_command_with_argument, 0))
    QtCore.QTimer.singleShot(400, lambda: qdevio.add_to_send_queue(dev.fake_command_with_argument, 0))
    QtCore.QTimer.singleShot(500, lambda: qdevio.add_to_send_queue(dev.fake_command_with_argument, 0))
    QtCore.QTimer.singleShot(600, lambda: qdevio.process_send_queue())
    QtCore.QTimer.singleShot(700, lambda: qdevio.send("trigger_illegal_function_call_error"))
    # fmt: on
    while time.perf_counter() - start_time < 1:
        app.processEvents()
        time.sleep(0.001)  # Do not hog the CPU

    tprint("About to quit")
    app.processEvents()
    assert qdevio.quit() == True
    app.quit()

    if start_alive:
        assert dev.count_commands == 5
        assert dev.count_replies == 2
        assert signal_counter == 4


def test_Worker_send__start_dead():
    test_Worker_send(start_alive=False)


def test_Worker_send__alt_jobs():
    print_title("Worker_send - alternative jobs")
    app = create_QApplication()

    # Simulate a device
    dev = FakeDevice()

    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True

    global signal_counter
    signal_counter = 0

    @QtCore.pyqtSlot()
    def process_send_updated():
        # In production code, your GUI update routine would go here
        tprint("---> Received signal: send_updated")
        global signal_counter
        signal_counter += 1

    qdevio.signal_send_updated.connect(process_send_updated)

    def jobs_function(func, args):
        if func == "special command":
            dev.fake_query()
        else:
            # Default job handling where, e.g.
            # func = self.dev.write
            # args = ("toggle LED",)
            func(*args)

    qdevio.create_worker_send(
        jobs_function=jobs_function, DEBUG=DEBUG,
    )

    assert qdevio.start() == True

    # Immediately fire a call to test if the worker is ready for it
    qdevio.send(dev.fake_query)

    # fmt: off
    # Simulate device runtime
    start_time = time.perf_counter()
    QtCore.QTimer.singleShot(100, lambda: qdevio.send("special command"))
    QtCore.QTimer.singleShot(200, lambda: qdevio.send(dev.fake_command_with_argument, 0))
    # fmt: on
    while time.perf_counter() - start_time < 0.5:
        app.processEvents()
        time.sleep(0.001)  # Do not hog the CPU

    tprint("About to quit")
    app.processEvents()
    assert qdevio.quit() == True
    app.quit()

    assert dev.count_commands == 3
    assert dev.count_replies == 2
    assert signal_counter == 3


def test_attach_device_twice():
    print_title("Attach device twice")
    import pytest

    dev = FakeDevice()
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True

    with pytest.raises(SystemExit) as pytest_wrapped_e:
        qdevio.attach_device(dev)
    assert pytest_wrapped_e.type == SystemExit
    dprint("Exit code: %i" % pytest_wrapped_e.value.code)
    assert pytest_wrapped_e.value.code == 22


def test_Worker_DAQ___no_device_attached():
    print_title("Worker_DAQ - no device attached")
    import pytest

    qdevio = DvG_QDeviceIO.QDeviceIO()

    with pytest.raises(SystemExit) as pytest_wrapped_e:
        qdevio.create_worker_DAQ()
    assert pytest_wrapped_e.type == SystemExit
    dprint("Exit code: %i" % pytest_wrapped_e.value.code)
    assert pytest_wrapped_e.value.code == 99


def test_Worker_send__no_device_attached():
    print_title("Worker_send - no device attached")
    import pytest

    qdevio = DvG_QDeviceIO.QDeviceIO()

    with pytest.raises(SystemExit) as pytest_wrapped_e:
        qdevio.create_worker_send()
    assert pytest_wrapped_e.type == SystemExit
    dprint("Exit code: %i" % pytest_wrapped_e.value.code)
    assert pytest_wrapped_e.value.code == 99


def test_Worker_DAQ___start_without_create():
    print_title("Worker_DAQ - start without create")
    import pytest

    dev = FakeDevice()
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True

    with pytest.raises(SystemExit) as pytest_wrapped_e:
        qdevio.start_worker_DAQ()
    assert pytest_wrapped_e.type == SystemExit
    dprint("Exit code: %i" % pytest_wrapped_e.value.code)
    assert pytest_wrapped_e.value.code == 404


def test_Worker_send__start_without_create():
    print_title("Worker_send - start without create")
    import pytest

    dev = FakeDevice()
    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True

    with pytest.raises(SystemExit) as pytest_wrapped_e:
        qdevio.start_worker_send()
    assert pytest_wrapped_e.type == SystemExit
    dprint("Exit code: %i" % pytest_wrapped_e.value.code)
    assert pytest_wrapped_e.value.code == 404


def test_Worker_DAQ___quit_without_start():
    print_title("Worker_DAQ - quit without start")
    app = create_QApplication()

    # Simulate a device
    dev = FakeDevice()

    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True

    qdevio.create_worker_DAQ()

    tprint("About to quit")
    app.processEvents()
    assert qdevio.quit() == True
    app.quit()


def test_Worker_send__quit_without_start():
    print_title("Worker_send - quit without start")
    app = create_QApplication()

    # Simulate a device
    dev = FakeDevice()

    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True

    qdevio.create_worker_send()

    tprint("About to quit")
    app.processEvents()
    assert qdevio.quit() == True
    app.quit()


def test_Worker_DAQ___rate():
    print_title("Worker_DAQ - INTERNAL_TIMER - DAQ rate")
    app = create_QApplication()

    # Simulate a device
    dev = FakeDevice()

    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True

    def DAQ_function():
        dprint(qdevio.obtained_DAQ_interval_ms)
        dprint(qdevio.obtained_DAQ_rate_Hz)
        return True

    # fmt: off
    # Worker_DAQ in mode INTERNAL TIMER
    qdevio.create_worker_DAQ(
        DAQ_trigger                     = DvG_QDeviceIO.DAQ_trigger.INTERNAL_TIMER,
        DAQ_function                    = DAQ_function,
        DAQ_interval_ms                 = 20,
        DAQ_timer_type                  = QtCore.Qt.PreciseTimer,
        critical_not_alive_count        = 1,
        calc_DAQ_rate_every_N_iter      = 25,
        DEBUG                           = DEBUG)
    # fmt: on

    print(qdevio.worker_DAQ.calc_DAQ_rate_every_N_iter)
    assert qdevio.start() == True

    # Simulate device runtime
    start_time = time.perf_counter()
    while time.perf_counter() - start_time < 1.02:
        app.processEvents()
        time.sleep(0.001)  # Do not hog the CPU

    tprint("About to quit")
    app.processEvents()
    assert qdevio.quit() == True
    app.quit()

    assert (
        qdevio.obtained_DAQ_interval_ms
        >= 19 & qdevio.obtained_DAQ_interval_ms
        <= 21
    )
    assert round(qdevio.obtained_DAQ_rate_Hz) == 50


def test_Worker_DAQ___lose_connection():
    print_title("Worker_DAQ - INTERNAL_TIMER - lose connection")
    app = create_QApplication()

    # Simulate a device
    dev = FakeDevice()

    qdevio = DvG_QDeviceIO.QDeviceIO()
    assert qdevio.attach_device(dev) == True

    def DAQ_function():
        if qdevio.update_counter_DAQ == 30:
            dev.is_alive = False
        reply = dev.fake_query()
        dprint(qdevio.obtained_DAQ_interval_ms)
        dprint(qdevio.obtained_DAQ_rate_Hz)
        return reply[-14:] == "device replied"

    # fmt: off
    # Worker_DAQ in mode INTERNAL TIMER
    qdevio.create_worker_DAQ(
        DAQ_trigger                     = DvG_QDeviceIO.DAQ_trigger.INTERNAL_TIMER,
        DAQ_function                    = DAQ_function,
        DAQ_interval_ms                 = 20,
        DAQ_timer_type                  = QtCore.Qt.PreciseTimer,
        critical_not_alive_count        = 3,
        calc_DAQ_rate_every_N_iter      = 20,
        DEBUG                           = DEBUG)
    # fmt: on

    # NOTE: The global 'go' mechanism used here is a quick and dirty way to
    # pytest. In production, it should be implemented by an boolean external
    # class member.
    global go
    go = True

    @QtCore.pyqtSlot()
    def process_connection_lost():
        tprint("---> Received signal: connection_lost")
        global go
        go = False

    qdevio.signal_connection_lost.connect(process_connection_lost)

    assert qdevio.start() == True

    # Simulate device runtime
    while go:
        app.processEvents()
        time.sleep(0.001)  # Do not hog the CPU

    tprint("About to quit")
    app.processEvents()
    assert qdevio.quit() == True
    app.quit()


if __name__ == "__main__":
    ALL = True
    if ALL:
        test_Worker_DAQ___INTERNAL_TIMER()
        test_Worker_DAQ___INTERNAL_TIMER__start_dead()
        test_Worker_DAQ___SINGLE_SHOT_WAKE_UP()
        test_Worker_DAQ___SINGLE_SHOT_WAKE_UP__start_dead()
        test_Worker_DAQ___CONTINUOUS()
        test_Worker_DAQ___CONTINUOUS__start_dead()
        test_Worker_send()
        test_Worker_send__start_dead()
        test_Worker_send__alt_jobs()
        test_attach_device_twice()
        test_Worker_DAQ___no_device_attached()
        test_Worker_send__no_device_attached()
        test_Worker_DAQ___start_without_create()
        test_Worker_send__start_without_create()
        test_Worker_DAQ___quit_without_start()
        test_Worker_send__quit_without_start()
        test_Worker_DAQ___rate()
        test_Worker_DAQ___lose_connection()
    else:
        # test_Worker_DAQ___INTERNAL_TIMER()
        # test_Worker_DAQ___INTERNAL_TIMER__start_dead()
        # test_Worker_DAQ___SINGLE_SHOT_WAKE_UP()
        # test_Worker_DAQ___SINGLE_SHOT_WAKE_UP__start_dead()

        """
        import msvcrt
        while True:
            test_Worker_DAQ___CONTINUOUS()
            if msvcrt.kbhit() and msvcrt.getch() == chr(27).encode():
                break
        """

        test_Worker_DAQ___CONTINUOUS()
        # test_Worker_DAQ___CONTINUOUS__start_dead()

        # test_Worker_DAQ___rate()
        # test_Worker_DAQ___lose_connection()
        # test_Worker_DAQ___no_device_attached()
        # test_Worker_DAQ___start_without_create()

        # test_Worker_send()
        # test_Worker_send__start_dead()
        # test_Worker_send__alt_jobs()
        # test_Worker_send__no_device_attached()
        # test_Worker_send__start_without_create()

        # test_Worker_DAQ___quit_without_start()
        # test_Worker_send__quit_without_start()

        # test_attach_device_twice()
