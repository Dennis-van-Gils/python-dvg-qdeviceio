#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time

# Mechanism to support both PyQt and PySide
# -----------------------------------------
import os
import sys

QT_LIB = os.getenv("PYQTGRAPH_QT_LIB")
PYSIDE = "PySide"
PYSIDE2 = "PySide2"
PYSIDE6 = "PySide6"
PYQT4 = "PyQt4"
PYQT5 = "PyQt5"
PYQT6 = "PyQt6"

# pylint: disable=import-error, no-name-in-module
# fmt: off
if QT_LIB is None:
    libOrder = [PYQT5, PYSIDE2, PYSIDE6, PYQT6]
    for lib in libOrder:
        if lib in sys.modules:
            QT_LIB = lib
            break

if QT_LIB is None:
    for lib in libOrder:
        try:
            __import__(lib)
            QT_LIB = lib
            break
        except ImportError:
            pass

if QT_LIB is None:
    raise Exception(
        "DvG_QDeviceIO requires PyQt5, PyQt6, PySide2 or PySide6; none of "
        "these packages could be imported."
    )

if QT_LIB == PYQT5:
    from PyQt5 import QtCore                               # type: ignore
    from PyQt5.QtCore import pyqtSlot as Slot              # type: ignore
    from PyQt5.QtCore import pyqtSignal as Signal          # type: ignore
elif QT_LIB == PYQT6:
    from PyQt6 import QtCore                               # type: ignore
    from PyQt6.QtCore import pyqtSlot as Slot              # type: ignore
    from PyQt6.QtCore import pyqtSignal as Signal          # type: ignore
elif QT_LIB == PYSIDE2:
    from PySide2 import QtCore                             # type: ignore
    from PySide2.QtCore import Slot                        # type: ignore
    from PySide2.QtCore import Signal                      # type: ignore
elif QT_LIB == PYSIDE6:
    from PySide6 import QtCore                             # type: ignore
    from PySide6.QtCore import Slot                        # type: ignore
    from PySide6.QtCore import Signal                      # type: ignore

# fmt: on
# pylint: enable=import-error, no-name-in-module
# \end[Mechanism to support both PyQt and PySide]
# -----------------------------------------------

from dvg_qdeviceio import QDeviceIO, DAQ_TRIGGER
from dvg_debug_functions import dprint, tprint, ANSI

# Show extra debug info in terminal?
DEBUG = True

global cnt_DAQ_updated, cnt_jobs_updated, cnt_DAQ_paused


@Slot()
def process_DAQ_updated():
    # In production code, your GUI update routine would go here
    tprint("---> received: DAQ_updated")
    global cnt_DAQ_updated
    cnt_DAQ_updated += 1


@Slot()
def process_DAQ_paused():
    # In production code, your GUI update routine would go here
    tprint("---> received: DAQ_paused")
    global cnt_DAQ_paused
    cnt_DAQ_paused += 1


@Slot()
def process_jobs_updated():
    # In production code, your GUI update routine would go here
    tprint("---> received: jobs_updated")
    global cnt_jobs_updated
    cnt_jobs_updated += 1


class FakeDevice:
    def __init__(self, start_alive=True):
        self.name = "FakeDev"
        self.is_alive = start_alive

        # Member for testing
        self.count_commands = 0
        self.count_replies = 0

    def _send(self, data_to_be_send):
        if self.is_alive:
            # Simulate successful device output
            self.count_replies += 1
            tprint_tab(data_to_be_send)
            return data_to_be_send
        else:
            # Simulate device failure
            time.sleep(0.1)
            tprint_tab("SIMULATED I/O ERROR")
            return "SIMULATED I/O ERROR"

    def fake_query_1(self):
        self.count_commands += 1
        return self._send("-> reply 0101")

    def fake_query_2(self):
        self.count_commands += 1
        return self._send("-> reply ~~~~")

    def fake_command_with_argument(self, val: int):
        tprint_tab("-> command(arg=%i)" % val)
        self.count_commands += 1


def create_QApplication():
    QtCore.QThread.currentThread().setObjectName("MAIN")  # For DEBUG info

    # QtWidgets are not needed for pytest and will fail standard Travis test
    # (X) app = QtWidgets.QApplication(sys.argv)
    # Use QCoreApplication instead
    if QtCore.QCoreApplication.instance():
        # Use already existing application
        app = QtCore.QCoreApplication.instance()
    else:
        app = QtCore.QCoreApplication(sys.argv)

    global cnt_DAQ_updated, cnt_DAQ_paused, cnt_jobs_updated
    cnt_DAQ_updated = 0
    cnt_DAQ_paused = 0
    cnt_jobs_updated = 0

    return app


def print_title(title):
    dprint("\n%s" % title, ANSI.PURPLE)
    dprint("-" * 50, ANSI.PURPLE)


def tprint_tab(str_msg, ANSI_color=None):
    dprint(" " * 60 + "%.4f %s" % (time.perf_counter(), str_msg), ANSI_color)


# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------


def test_Worker_DAQ___INTERNAL_TIMER(start_alive=True):
    print_title(
        "Worker_DAQ - INTERNAL_TIMER" + ("" if start_alive else " - start dead")
    )

    def DAQ_function():
        # Must return True when successful, False otherwise
        reply = dev.fake_query_1()
        return reply[-4:] == "0101"

    app = create_QApplication()
    dev = FakeDevice(start_alive=start_alive)
    qdev = QDeviceIO(dev)
    # fmt: off
    qdev.create_worker_DAQ(
        DAQ_trigger                = DAQ_TRIGGER.INTERNAL_TIMER,
        DAQ_function               = DAQ_function,
        DAQ_interval_ms            = 100,
        critical_not_alive_count   = 10,
        debug                      = DEBUG)
    # fmt: on
    qdev.signal_DAQ_updated.connect(process_DAQ_updated)
    assert qdev.start() == start_alive

    # Simulate device runtime
    start_time = time.perf_counter()
    while time.perf_counter() - start_time < 1:
        app.processEvents()
        if dev.count_commands == 3:
            break
        time.sleep(0.001)  # Do not hog the CPU

    tprint("About to quit")
    app.processEvents()
    assert qdev.quit() == True
    app.quit()

    if start_alive:
        assert dev.count_commands >= 3
        assert dev.count_replies >= 3
        assert (
            cnt_DAQ_updated >= 2
        )  # Last signal is not always received before thread is quit


def test_Worker_DAQ___INTERNAL_TIMER__start_dead():
    test_Worker_DAQ___INTERNAL_TIMER(start_alive=False)


def test_Worker_DAQ___SINGLE_SHOT_WAKE_UP(start_alive=True):
    print_title(
        "Worker_DAQ - SINGLE_SHOT_WAKE_UP"
        + ("" if start_alive else " - start dead")
    )

    def DAQ_function():
        # Must return True when successful, False otherwise
        reply = dev.fake_query_1()
        return reply[-4:] == "0101"

    app = create_QApplication()
    dev = FakeDevice(start_alive=start_alive)
    qdev = QDeviceIO(dev)
    # fmt: off
    qdev.create_worker_DAQ(
        DAQ_trigger                = DAQ_TRIGGER.SINGLE_SHOT_WAKE_UP,
        DAQ_function               = DAQ_function,
        critical_not_alive_count   = 1,
        debug                      = DEBUG)
    # fmt: on
    qdev.signal_DAQ_updated.connect(process_DAQ_updated)
    assert qdev.start() == start_alive

    # Immediately fire a call to test if the worker is ready for it
    qdev.wake_up_DAQ()

    # Simulate device runtime
    start_time = time.perf_counter()
    QtCore.QTimer.singleShot(300, qdev.wake_up_DAQ)
    QtCore.QTimer.singleShot(600, qdev.wake_up_DAQ)
    while time.perf_counter() - start_time < 1:
        app.processEvents()
        time.sleep(0.001)  # Do not hog the CPU

    tprint("About to quit")
    app.processEvents()
    assert qdev.quit() == True
    app.quit()

    if start_alive:
        assert dev.count_commands == 3
        assert dev.count_replies == 3
        assert cnt_DAQ_updated == 3


def test_Worker_DAQ___SINGLE_SHOT_WAKE_UP__start_dead():
    test_Worker_DAQ___SINGLE_SHOT_WAKE_UP(start_alive=False)


def test_Worker_DAQ___CONTINUOUS(start_alive=True):
    print_title(
        "Worker_DAQ - CONTINUOUS" + ("" if start_alive else " - start dead")
    )

    def DAQ_function():
        # Must return True when successful, False otherwise
        time.sleep(0.1)  # Simulate blocking processing time on the device
        reply = dev.fake_query_1()
        return reply[-4:] == "0101"

    app = create_QApplication()
    dev = FakeDevice(start_alive=start_alive)
    qdev = QDeviceIO(dev)
    # fmt: off
    qdev.create_worker_DAQ(
        DAQ_trigger                = DAQ_TRIGGER.CONTINUOUS,
        DAQ_function               = DAQ_function,
        critical_not_alive_count   = 1,
        debug                      = DEBUG,
    )
    # fmt: on

    qdev.signal_DAQ_updated.connect(process_DAQ_updated)
    qdev.signal_DAQ_paused.connect(process_DAQ_paused)

    assert qdev.start() == start_alive

    # Immediately fire a call to test if the worker is ready for it
    qdev.unpause_DAQ()

    # Simulate device runtime
    start_time = time.perf_counter()
    QtCore.QTimer.singleShot(300, qdev.pause_DAQ)
    QtCore.QTimer.singleShot(600, qdev.unpause_DAQ)
    QtCore.QTimer.singleShot(900, qdev.pause_DAQ)
    QtCore.QTimer.singleShot(1200, qdev.unpause_DAQ)
    while time.perf_counter() - start_time < 1.6:
        app.processEvents()
        if dev.count_commands == 12:
            break
        time.sleep(0.001)  # Do not hog the CPU

    tprint("About to quit")
    app.processEvents()
    assert qdev.quit() == True
    app.quit()

    if start_alive:
        assert dev.count_commands >= 10
        assert dev.count_replies >= 10
        assert (
            cnt_DAQ_updated >= 9
        )  # Last signal is not always received before thread is quit
        assert cnt_DAQ_paused == 3


def test_Worker_DAQ___CONTINUOUS__start_dead():
    test_Worker_DAQ___CONTINUOUS(start_alive=False)


def test_Worker_jobs(start_alive=True):
    print_title("Worker_jobs" + ("" if start_alive else " - start dead"))

    app = create_QApplication()
    dev = FakeDevice(start_alive=start_alive)
    qdev = QDeviceIO(dev)
    qdev.create_worker_jobs(debug=DEBUG)
    qdev.signal_jobs_updated.connect(process_jobs_updated)
    assert qdev.start() == start_alive

    # Immediately fire a call to test if the worker is ready for it
    qdev.add_to_jobs_queue(dev.fake_query_2)

    # fmt: off
    # Simulate device runtime
    start_time = time.perf_counter()
    QtCore.QTimer.singleShot(100, qdev.process_jobs_queue)
    QtCore.QTimer.singleShot(200, lambda: qdev.send(dev.fake_query_2))
    QtCore.QTimer.singleShot(300, lambda: qdev.add_to_jobs_queue(dev.fake_command_with_argument, 0))
    QtCore.QTimer.singleShot(400, lambda: qdev.add_to_jobs_queue(dev.fake_command_with_argument, 0))
    QtCore.QTimer.singleShot(500, lambda: qdev.add_to_jobs_queue(dev.fake_command_with_argument, 0))
    QtCore.QTimer.singleShot(600, qdev.process_jobs_queue)
    QtCore.QTimer.singleShot(700, lambda: qdev.send("trigger_illegal_function_call_error"))
    # fmt: on
    while time.perf_counter() - start_time < 1:
        app.processEvents()
        time.sleep(0.001)  # Do not hog the CPU

    tprint("About to quit")
    app.processEvents()
    assert qdev.quit() == True
    app.quit()

    if start_alive:
        assert dev.count_commands == 5
        assert dev.count_replies == 2
        assert cnt_jobs_updated == 4


def test_Worker_jobs__start_dead():
    test_Worker_jobs(start_alive=False)


def test_Worker_jobs__jobs_function():
    print_title("Worker_jobs - jobs_function")

    def jobs_function(func, args):
        if func == "special command":
            dev.fake_query_2()
        else:
            # Default job handling where, e.g.
            # func = self.dev.write
            # args = ("toggle LED",)
            func(*args)

    app = create_QApplication()
    dev = FakeDevice()
    qdev = QDeviceIO(dev)
    qdev.create_worker_jobs(
        jobs_function=jobs_function,
        debug=DEBUG,
    )
    qdev.signal_jobs_updated.connect(process_jobs_updated)
    assert qdev.start() == True

    # Immediately fire a call to test if the worker is ready for it
    qdev.send(dev.fake_query_2)

    # fmt: off
    # Simulate device runtime
    start_time = time.perf_counter()
    QtCore.QTimer.singleShot(100, lambda: qdev.send("special command"))
    QtCore.QTimer.singleShot(200, lambda: qdev.send(dev.fake_command_with_argument, 0))
    # fmt: on
    while time.perf_counter() - start_time < 0.5:
        app.processEvents()
        time.sleep(0.001)  # Do not hog the CPU

    tprint("About to quit")
    app.processEvents()
    assert qdev.quit() == True
    app.quit()

    assert dev.count_commands == 3
    assert dev.count_replies == 2
    assert cnt_jobs_updated == 3


def test_attach_device_twice():
    print_title("Attach device twice")
    import pytest

    qdev = QDeviceIO(FakeDevice())

    with pytest.raises(SystemExit) as pytest_wrapped_e:
        qdev.attach_device(FakeDevice())
    assert pytest_wrapped_e.type == SystemExit
    dprint("Exit code: %i" % pytest_wrapped_e.value.code)
    assert pytest_wrapped_e.value.code == 22


def test_Worker_DAQ___no_device_attached():
    print_title("Worker_DAQ - no device attached")
    import pytest

    qdev = QDeviceIO()

    with pytest.raises(SystemExit) as pytest_wrapped_e:
        qdev.create_worker_DAQ()
    assert pytest_wrapped_e.type == SystemExit
    dprint("Exit code: %i" % pytest_wrapped_e.value.code)
    assert pytest_wrapped_e.value.code == 99


def test_Worker_jobs__no_device_attached():
    print_title("Worker_jobs - no device attached")
    import pytest

    qdev = QDeviceIO()

    with pytest.raises(SystemExit) as pytest_wrapped_e:
        qdev.create_worker_jobs()
    assert pytest_wrapped_e.type == SystemExit
    dprint("Exit code: %i" % pytest_wrapped_e.value.code)
    assert pytest_wrapped_e.value.code == 99


def test_Worker_DAQ___start_without_create():
    print_title("Worker_DAQ - start without create")
    import pytest

    qdev = QDeviceIO(FakeDevice())

    with pytest.raises(SystemExit) as pytest_wrapped_e:
        qdev.start_worker_DAQ()
    assert pytest_wrapped_e.type == SystemExit
    dprint("Exit code: %i" % pytest_wrapped_e.value.code)
    assert pytest_wrapped_e.value.code == 404


def test_Worker_jobs__start_without_create():
    print_title("Worker_jobs - start without create")
    import pytest

    qdev = QDeviceIO(FakeDevice())

    with pytest.raises(SystemExit) as pytest_wrapped_e:
        qdev.start_worker_jobs()
    assert pytest_wrapped_e.type == SystemExit
    dprint("Exit code: %i" % pytest_wrapped_e.value.code)
    assert pytest_wrapped_e.value.code == 404


def test_Worker_DAQ___quit_without_start():
    print_title("Worker_DAQ - quit without start")

    app = create_QApplication()
    qdev = QDeviceIO(FakeDevice())
    qdev.create_worker_DAQ()

    tprint("About to quit")
    app.processEvents()
    assert qdev.quit() == True
    app.quit()


def test_Worker_jobs__quit_without_start():
    print_title("Worker_jobs - quit without start")

    app = create_QApplication()
    qdev = QDeviceIO(FakeDevice())
    qdev.create_worker_jobs()

    tprint("About to quit")
    app.processEvents()
    assert qdev.quit() == True
    app.quit()


def test_Worker_DAQ___rate():
    print_title("Worker_DAQ - INTERNAL_TIMER - DAQ rate")

    def DAQ_function():
        # Must return True when successful, False otherwise
        reply = dev.fake_query_1()
        dprint(" " * 50 + "%.1f Hz" % qdev.obtained_DAQ_rate_Hz)
        return reply[-4:] == "0101"

    app = create_QApplication()
    dev = FakeDevice()
    qdev = QDeviceIO(dev)
    # fmt: off
    qdev.create_worker_DAQ(
        DAQ_trigger                = DAQ_TRIGGER.INTERNAL_TIMER,
        DAQ_function               = DAQ_function,
        DAQ_interval_ms            = 10,
        critical_not_alive_count   = 1,
        debug                      = DEBUG)
    # fmt: on
    assert qdev.start() == True

    # Simulate device runtime
    start_time = time.perf_counter()
    while time.perf_counter() - start_time < 1.51:
        app.processEvents()
        time.sleep(0.001)  # Do not hog the CPU

    tprint("About to quit")
    app.processEvents()
    assert qdev.quit() == True
    app.quit()

    assert 9 <= qdev.obtained_DAQ_interval_ms <= 11
    assert 99 <= qdev.obtained_DAQ_rate_Hz <= 101


def test_Worker_DAQ___lose_connection():
    print_title("Worker_DAQ - INTERNAL_TIMER - lose connection")

    def DAQ_function():
        # Must return True when successful, False otherwise
        if qdev.update_counter_DAQ == 10:
            dev.is_alive = False

        reply = dev.fake_query_1()
        return reply[-4:] == "0101"

    # NOTE: The global 'go' mechanism used here is a quick and dirty way to
    # pytest. In production, it should be implemented by an boolean external
    # class member.
    global go
    go = True

    @Slot()
    def process_connection_lost():
        tprint("---> received: connection_lost")
        global go
        go = False

    app = create_QApplication()
    dev = FakeDevice()

    # Forcefully remove members as extra test
    del dev.name
    del dev.is_alive

    qdev = QDeviceIO(dev)
    # fmt: off
    qdev.create_worker_DAQ(
        DAQ_trigger                = DAQ_TRIGGER.INTERNAL_TIMER,
        DAQ_function               = DAQ_function,
        DAQ_interval_ms            = 20,
        critical_not_alive_count   = 3,
        debug                      = DEBUG)
    # fmt: on
    qdev.create_worker_jobs(debug=DEBUG)
    qdev.signal_connection_lost.connect(process_connection_lost)
    assert qdev.start() == True

    # Simulate device runtime
    while go:
        app.processEvents()
        time.sleep(0.001)  # Do not hog the CPU

    tprint("About to quit")
    app.processEvents()
    assert qdev.quit() == True
    assert qdev.quit() == True  # Twice, to check for msg 'already closed'.
    app.quit()


class QDeviceIO_subclassed(QDeviceIO):
    def __init__(
        self,
        dev=None,
        DAQ_function=None,
        debug=False,
        **kwargs,
    ):
        # Pass `dev` onto QDeviceIO() and pass `**kwargs` onto QtCore.QObject()
        super().__init__(dev, **kwargs)

        # fmt: off
        self.create_worker_DAQ(
            DAQ_trigger                = DAQ_TRIGGER.INTERNAL_TIMER,
            DAQ_function               = DAQ_function,
            DAQ_interval_ms            = 100,
            critical_not_alive_count   = 10,
            debug                      = DEBUG,
        )
        # fmt: on
        self.create_worker_jobs(debug=DEBUG)


def test_Worker_DAQ___INTERNAL_TIMER__subclassed():
    print_title("Worker_DAQ - INTERNAL_TIMER - subclassed")

    def DAQ_function():
        # Must return True when successful, False otherwise
        reply = dev.fake_query_1()
        return reply[-4:] == "0101"

    app = create_QApplication()
    dev = FakeDevice()
    qdev = QDeviceIO_subclassed(
        dev=dev,
        DAQ_function=DAQ_function,
        debug=DEBUG,
    )
    qdev.signal_DAQ_updated.connect(process_DAQ_updated)
    qdev.signal_jobs_updated.connect(process_jobs_updated)
    qdev.start()

    # fmt: off
    # Simulate device runtime
    start_time = time.perf_counter()
    QtCore.QTimer.singleShot(300, lambda: qdev.send(dev.fake_query_2))
    QtCore.QTimer.singleShot(600, lambda: qdev.send(dev.fake_command_with_argument, 0))
    # fmt: on
    while time.perf_counter() - start_time < 1:
        app.processEvents()
        time.sleep(0.001)  # Do not hog the CPU

    tprint("About to quit")
    app.processEvents()
    assert qdev.quit() == True
    app.quit()

    assert dev.count_commands >= 11
    assert dev.count_replies >= 10
    assert (
        cnt_DAQ_updated >= 9
    )  # Last signal is not always received before thread is quit
    assert cnt_jobs_updated == 2


def test_Worker_DAQ___ILLEGAL_DAQ_FUNCTION():
    print_title("Worker_DAQ - ILLEGAL_DAQ_FUNCTION")

    def DAQ_function():
        # Must return True when successful, False otherwise

        if qdev.update_counter_DAQ == 2:
            0 / 0
        else:
            reply = dev.fake_query_1()
            return reply[-4:] == "0101"

    app = create_QApplication()
    dev = FakeDevice()
    qdev = QDeviceIO(dev)
    # fmt: off
    qdev.create_worker_DAQ(
        DAQ_trigger                = DAQ_TRIGGER.INTERNAL_TIMER,
        DAQ_function               = DAQ_function,
        DAQ_interval_ms            = 100,
        debug                      = DEBUG)
    # fmt: on
    qdev.signal_DAQ_updated.connect(process_DAQ_updated)
    assert qdev.start() == True

    # Simulate device runtime
    start_time = time.perf_counter()
    while time.perf_counter() - start_time < 1:
        app.processEvents()
        if dev.count_commands == 3:
            break
        time.sleep(0.001)  # Do not hog the CPU

    tprint("About to quit")
    app.processEvents()
    assert qdev.quit() == True
    app.quit()


# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------


if __name__ == "__main__":
    ALL = True
    if ALL:
        test_Worker_DAQ___INTERNAL_TIMER()
        test_Worker_DAQ___INTERNAL_TIMER__start_dead()
        test_Worker_DAQ___SINGLE_SHOT_WAKE_UP()
        test_Worker_DAQ___SINGLE_SHOT_WAKE_UP__start_dead()
        test_Worker_DAQ___CONTINUOUS()
        test_Worker_DAQ___CONTINUOUS__start_dead()
        test_Worker_jobs()
        test_Worker_jobs__start_dead()
        test_Worker_jobs__jobs_function()
        test_attach_device_twice()
        test_Worker_DAQ___no_device_attached()
        test_Worker_jobs__no_device_attached()
        test_Worker_DAQ___start_without_create()
        test_Worker_jobs__start_without_create()
        test_Worker_DAQ___quit_without_start()
        test_Worker_jobs__quit_without_start()
        test_Worker_DAQ___rate()
        test_Worker_DAQ___lose_connection()
        test_Worker_DAQ___INTERNAL_TIMER__subclassed()
        test_Worker_DAQ___ILLEGAL_DAQ_FUNCTION()
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

        # test_Worker_jobs()
        # test_Worker_jobs__start_dead()
        # test_Worker_jobs__jobs_function()
        # test_Worker_jobs__no_device_attached()
        # test_Worker_jobs__start_without_create()

        # test_Worker_DAQ___quit_without_start()
        # test_Worker_jobs__quit_without_start()

        # test_attach_device_twice()

        # test_Worker_DAQ___INTERNAL_TIMER__subclassed()
        # test_Worker_DAQ___lose_connection()
        # test_Worker_DAQ___ILLEGAL_DAQ_FUNCTION()
