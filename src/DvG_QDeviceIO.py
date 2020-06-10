#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt5 framework for multithreaded periodical data acquisition and
communication with an I/O device.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-qdeviceio"
__date__ = "10-06-2020"
__version__ = "0.0.9"  # v0.0.1 on PyPI is based on prototype DvG_dev_Base__pyqt_lib.py v1.3.3

from enum import IntEnum, unique
import queue
import time

# Code coverage tools 'coverage' and 'pytest-cov' don't seem to correctly trace
# code which is inside methods called from within QThreads, see
# https://github.com/nedbat/coveragepy/issues/686
# To mitigate this problem, I use a custom decorator '@_coverage_resolve_trace'
# to be hung onto those method definitions. This will prepend the decorated
# method code with 'sys.settrace(threading._trace_hook)' when a code
# coverage test is detected. When no coverage test is detected, it will just
# pass the original method untouched.
import sys
import threading
from functools import wraps

running_coverage = "coverage" in sys.modules
if running_coverage:
    print("\nCode coverage test detected\n")


def _coverage_resolve_trace(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if running_coverage:
            sys.settrace(threading._trace_hook)
        fn(*args, **kwargs)

    return wrapped


import numpy as np
from PyQt5 import QtCore
from DvG_debug_functions import (
    print_fancy_traceback as pft,
    dprint,
    tprint,
    ANSI,
)

# Short-hand alias for DEBUG information
def _cur_thread_name():
    return QtCore.QThread.currentThread().objectName()


@unique
class DAQ_trigger(IntEnum):
    [INTERNAL_TIMER, SINGLE_SHOT_WAKE_UP, CONTINUOUS] = range(3)


# ------------------------------------------------------------------------------
#   QDeviceIO
# ------------------------------------------------------------------------------


class QDeviceIO(QtCore.QObject):
    """This class provides the base framework for multithreaded communication
    and periodical data acquisition for an I/O device.

    All device I/O operations will be offloaded to 'workers', each running in
    a newly created and dedicated thread.

    * :obj:`Worker_DAQ`:
        Periodically acquires data from the device.

    * :obj:`Worker_send`:
        Maintains a thread-safe queue where desired device I/O operations
        can be put onto, and sends the queued operations first in first out
        (FIFO) to the device.
        
    Example:
        This class can be mixed into your own specific ``QDeviceIO`` class,
        e.g., for a specific Arduino project::
        
            class QDeviceIO_Arduino(DvG_QDeviceIO.QDeviceIO, QtCore.QObject):
                def __init__(
                    self, dev=None, DAQ_function=None, DEBUG=False, parent=None,
                ):
                    super(QDeviceIO_Arduino, self).__init__(parent=parent)
    
                    self.attach_device(dev)
                    
                    self.create_worker_DAQ(
                        DAQ_trigger                = DAQ_trigger.INTERNAL_TIMER,
                        DAQ_function               = DAQ_function,
                        DAQ_interval_ms            = 100,
                        DAQ_timer_type             = QtCore.Qt.PreciseTimer,
                        critical_not_alive_count   = 10,
                        calc_DAQ_rate_every_N_iter = 5,
                        DEBUG                      = DEBUG,
                    )            
                    self.create_worker_send(DEBUG=DEBUG)

    Args:
        dev (:obj:`object`):
            Reference to a user-supplied *device* class instance containing I/O
            methods. In addition, ``dev`` should also have the following
            members:
            
                ``dev.name`` (:obj:`str`):
                    Short display name for the device.            
                ``dev.mutex`` (:obj:`PyQt5.QtCore.QMutex`):
                    To allow for properly multithreaded device I/O operations.
                    It will be used by ``Worker_DAQ`` and ``Worker_send``.
                ``dev.is_alive`` (:obj:`bool`):
                    Device is up and communicatable?

    Attributes:
        dev (:obj:`object`):
            Reference to a user-supplied *device* class instance containing your
            I/O methods.
        
        worker_DAQ (:obj:`Worker_DAQ`):
            Periodically acquires data from the device. Runs in a dedicated
            thread.
        
        worker_send (:obj:`Worker_send`):
             Maintains a thread-safe queue where desired device I/O operations
             can be put onto, and sends the queued operations first in first out
             (FIFO) to the device. Runs in a dedicated thread.
        
        update_counter_DAQ (:obj:`int`):
            Increments every time ``worker_DAQ`` tries to update.
        
        update_counter_send (:obj:`int`):
            Increments every time ``worker_send`` tries to update.
        
        obtained_DAQ_interval_ms:
            Obtained time interval in milliseconds since the previous
            ``worker_DAQ`` update.
        
        obtained_DAQ_rate_Hz:
            Obtained acquisition rate of ``worker_DAQ`` in Hertz.

    :Signals:
        Type: :obj:`PyQt5.QtCore.pyqtSignal`
        
        :obj:`signal_DAQ_updated()`            
        
        :obj:`signal_send_updated()`            
        
        :obj:`signal_DAQ_paused()`        
        
        :obj:`signal_connection_lost()`
    """

    signal_DAQ_updated = QtCore.pyqtSignal()
    """:obj:`PyQt5.QtCore.pyqtSignal`: Emitted by ``worker_DAQ`` when the
    :obj:`DAQ_function` has run and has finished succesfully.
    
    Tip:
        It can be useful to connect this signal to your own slot containing
        your GUI redraw routine, as such::
            
            qdeviceio.signal_DAQ_updated.connect(my_GUI_redraw_routine)
            
        where ``qdeviceio`` is your instance of :obj:`QDeviceIO`.
    """

    signal_DAQ_paused = QtCore.pyqtSignal()
    """:obj:`PyQt5.QtCore.pyqtSignal`: Emitted by ``worker_DAQ`` to confirm the
    worker has entered the `paused` state as a response to :obj:`pause_DAQ()`.
    """

    signal_connection_lost = QtCore.pyqtSignal()
    """:obj:`PyQt5.QtCore.pyqtSignal`: Emitted by ``worker_DAQ`` to indicate
    that we lost connection to the device. This happens when `N` consecutive
    device I/O operations have failed, where `N` equals the argument
    :obj:`critical_not_alive_count` as passed to method
    :obj:`create_worker_DAQ()`.
    """

    signal_send_updated = QtCore.pyqtSignal()
    """:obj:`PyQt5.QtCore.pyqtSignal`: Emitted by ``worker_send`` when all
    pending jobs in the queue have been sent out to the device as a response to
    :obj:`send()` or :obj:`process_send_queue()`.
    """

    # Necessary for INTERNAL_TIMER
    _signal_stop_worker_DAQ = QtCore.pyqtSignal()

    def __init__(self, dev=None, parent=None):
        super(QDeviceIO, self).__init__(parent=parent)

        self.dev = self._NoDevice()
        if dev is not None:
            self.attach_device(dev)

        self._thread_DAQ = None
        self._thread_send = None

        self.worker_DAQ = None
        self.worker_send = None

        self.update_counter_DAQ = 0
        self.update_counter_send = 0
        self.not_alive_counter_DAQ = 0

        self.obtained_DAQ_interval_ms = np.nan
        self.obtained_DAQ_rate_Hz = np.nan

        self._qwc_worker_DAQ_started = QtCore.QWaitCondition()
        self._qwc_worker_send_started = QtCore.QWaitCondition()

        self._qwc_worker_DAQ_stopped = QtCore.QWaitCondition()
        self._qwc_worker_send_stopped = QtCore.QWaitCondition()
        self._mutex_wait_worker_DAQ = QtCore.QMutex()
        self._mutex_wait_worker_send = QtCore.QMutex()

    class _NoDevice:
        name = "NoDevice"
        mutex = QtCore.QMutex()
        is_alive = False

    # --------------------------------------------------------------------------
    #   attach_device
    # --------------------------------------------------------------------------

    def attach_device(self, dev):
        """Attaches a reference to a *device* instance containing your I/O
        methods.
        
        Args:
            dev (:obj:`object`):
                Reference to a user-supplied *device* class instance containing
                your I/O methods.
        
        Returns:
            True if successful, False otherwise.
        """
        if type(self.dev) == self._NoDevice:
            self.dev = dev
            # TODO: Test for existence required members
            # dev.name, dev.mutex, dev.is_alive
            return True
        else:
            pft(
                "Device can be attached only once. Already attached to '%s'."
                % self.dev.name
            )
            sys.exit(22)

    # --------------------------------------------------------------------------
    #   Create workers
    # --------------------------------------------------------------------------

    def create_worker_DAQ(self, **kwargs):
        """Creates and configures an instance of :obj:`Worker_DAQ` and transfers
        it to a newly created :obj:`PyQt5.QtCore.QThread`.

        Args:
            **kwargs
                Will be passed directly to :obj:`Worker_DAQ` as initialization
                parameters.
        """
        if type(self.dev) == self._NoDevice:
            pft(
                "Can't create worker_DAQ, because there is no device attached."
                " Did you forget to call 'attach_device()' first?"
            )
            sys.exit(99)

        self.worker_DAQ = Worker_DAQ(qdev=self, **kwargs)
        self._signal_stop_worker_DAQ.connect(self.worker_DAQ._stop)

        self._thread_DAQ = QtCore.QThread()
        self._thread_DAQ.setObjectName("%s_DAQ" % self.dev.name)
        self._thread_DAQ.started.connect(self.worker_DAQ._do_work)
        self.worker_DAQ.moveToThread(self._thread_DAQ)

    def create_worker_send(self, **kwargs):
        """Creates and configures an instance of :obj:`Worker_send` and
        transfers it to a newly created :obj:`PyQt5.QtCore.QThread`.

        Args:
            **kwargs
                Will be passed directly to :obj:`Worker_send` as initialization
                parameters.
        """
        if type(self.dev) == self._NoDevice:
            pft(
                "Can't create worker_send, because there is no device attached."
                " Did you forget to call 'attach_device()' first?"
            )
            sys.exit(99)

        self.worker_send = Worker_send(qdev=self, **kwargs)

        self._thread_send = QtCore.QThread()
        self._thread_send.setObjectName("%s_send" % self.dev.name)
        self._thread_send.started.connect(self.worker_send._do_work)
        self.worker_send.moveToThread(self._thread_send)

    # --------------------------------------------------------------------------
    #   Start workers
    # --------------------------------------------------------------------------

    def start_worker_DAQ(self, priority=QtCore.QThread.InheritPriority):
        """Starts the periodical data acquisition with the device by starting
        the event loop of the ``worker_DAQ`` thread.

        Args:
            priority (:obj:`PyQt5.QtCore.QThread.Priority`, optional):
                See `start()`_.

        Returns:
            True if successful, False otherwise.
        """
        if self._thread_DAQ is None:
            pft(
                "Worker_DAQ %s: Can't start thread, because it does not exist. "
                "Did you forget to call 'create_worker_DAQ()' first?"
                % self.dev.name
            )
            sys.exit(404)

        elif not self.dev.is_alive:
            dprint(
                "\nWorker_DAQ %s: WARNING - Device is not alive.\n"
                % self.dev.name,
                ANSI.RED,
            )
            self.worker_DAQ._started_okay = False

        else:
            self.worker_DAQ._started_okay = True

        if self.worker_DAQ.DEBUG:
            tprint(
                "Worker_DAQ  %s: start requested..." % self.dev.name,
                ANSI.WHITE,
            )

        self._thread_DAQ.start(priority)

        # Wait for worker_DAQ to confirm having started
        locker_wait = QtCore.QMutexLocker(self._mutex_wait_worker_DAQ)
        self._qwc_worker_DAQ_started.wait(self._mutex_wait_worker_DAQ)
        locker_wait.unlock()

        if self.worker_DAQ._DAQ_trigger == DAQ_trigger.SINGLE_SHOT_WAKE_UP:
            # Wait a tiny amount of extra time for the worker to have entered
            # 'self._qwc.wait(self._mutex_wait)' of method '_do_work()'.
            # Unfortunately, we can't use
            #   'QTimer.singleShot(500, confirm_started(self))'
            # inside the '_do_work()' routine, because it won't never resolve
            # due to the upcoming blocking 'self._qwc.wait(self._mutex_wait)'.
            # Hence, we use a blocking 'time.sleep()' here. Also note we can't
            # use 'QtCore.QCoreApplication.processEvents()' instead of
            # 'time.sleep()', because it involves a QWaitCondition and not an
            # signal event.
            time.sleep(0.05)

        if self.worker_DAQ._DAQ_trigger == DAQ_trigger.CONTINUOUS:
            # We expect a 'signal_DAQ_paused' being emitted at start-up by this
            # worker. Make sure this signal gets processed as soon as possible,
            # and prior to any other subsequent actions the user might request
            # from this worker after having returned back from the user's call
            # to 'start_worker_DAQ()'.
            QtCore.QCoreApplication.processEvents()

        return self.worker_DAQ._started_okay

    def start_worker_send(self, priority=QtCore.QThread.InheritPriority):
        """Starts maintaining the desired device I/O operations queue by
        starting the event loop of the ``worker_send`` thread.

        Args:
            priority (:obj:`PyQt5.QtCore.QThread.Priority`, optional):
                See `start()`_.

        Returns:
            True if successful, False otherwise.
        """
        if self._thread_send is None:
            pft(
                "Worker_send %s: Can't start thread because it does not exist. "
                "Did you forget to call 'create_worker_send()' first?"
                % self.dev.name
            )
            sys.exit(404)

        elif not self.dev.is_alive:
            dprint(
                "\nWorker_send %s: WARNING - Device is not alive.\n"
                % self.dev.name,
                ANSI.RED,
            )
            self.worker_send._started_okay = False

        else:
            self.worker_send._started_okay = True

        if self.worker_send.DEBUG:
            tprint(
                "Worker_send %s: start requested..." % self.dev.name,
                ANSI.WHITE,
            )

        self._thread_send.start(priority)

        # Wait for worker_send to confirm having started
        locker_wait = QtCore.QMutexLocker(self._mutex_wait_worker_send)
        self._qwc_worker_send_started.wait(self._mutex_wait_worker_send)
        locker_wait.unlock()

        # Wait a tiny amount of extra time for the worker to have entered
        # 'self._qwc.wait(self._mutex_wait)' of method '_do_work()'.
        # Unfortunately, we can't use
        #   'QTimer.singleShot(500, confirm_started(self))'
        # inside the '_do_work()' routine, because it won't never resolve
        # due to the upcoming blocking 'self._qwc.wait(self._mutex_wait)'.
        # Hence, we use a blocking 'time.sleep()' here. Also note we can't
        # use 'QtCore.QCoreApplication.processEvents()' instead of
        # 'time.sleep()', because it involves a QWaitCondition and not an
        # signal event.
        time.sleep(0.05)

        return self.worker_send._started_okay

    def start(
        self,
        DAQ_priority=QtCore.QThread.InheritPriority,
        send_priority=QtCore.QThread.InheritPriority,
    ):
        """Starts the event loop of all of any created workers.
        
        .. _`start()`:
        
        Args:
            DAQ_priority (:obj:`PyQt5.QtCore.QThread.Priority`, optional):
                By default, the 'worker' thread runs in the operating system
                at the same thread priority as the main/GUI thread. You can
                change to higher priority by setting 'priority' to, e.g.,
                :obj:`QtCore.QThread.TimeCriticalPriority`. Be aware that this
                is resource heavy, so use sparingly.
            
            send_priority (:obj:`PyQt5.QtCore.QThread.Priority`, optional):
                See parameter :obj:`DAQ_priority`.
        
        Returns:
            True if successful, False otherwise.
        """
        success = True

        if self._thread_send is not None:
            success &= self.start_worker_send(priority=send_priority)

        if self._thread_DAQ is not None:
            success &= self.start_worker_DAQ(priority=DAQ_priority)

        return success

    # --------------------------------------------------------------------------
    #   Quit workers
    # --------------------------------------------------------------------------

    def quit_worker_DAQ(self):
        """Stops ``worker_DAQ`` and closes its thread.
        
        Returns:
            True if successful, False otherwise.
        """
        if self._thread_DAQ is None or self.worker_DAQ._started_okay is None:
            # CASE: quit() without create()
            #   _thread_DAQ == None
            #   _started_okay = None
            # CASE: quit() without start()
            #   _thread_DAQ == QThread()
            #   _started_okay = None
            return True

        # CASE: quit() with a device dead from the start
        #   _thread_DAQ == QThread()
        #   _started_okay = False

        # CASE: quit() with a device alive from the start
        #   _thread_DAQ == QThread()
        #   _started_okay = True

        if self.worker_DAQ.DEBUG:
            tprint(
                "Worker_DAQ  %s: stop requested..." % self.dev.name, ANSI.WHITE,
            )

        if self.worker_DAQ._DAQ_trigger == DAQ_trigger.INTERNAL_TIMER:
            # The QTimer inside the INTERNAL_TIMER '_do_work()'-routine /must/
            # be stopped from within the worker_DAQ thread. Hence, we must use a
            # signal from out of this different thread.
            self._signal_stop_worker_DAQ.emit()

        elif self.worker_DAQ._DAQ_trigger == DAQ_trigger.SINGLE_SHOT_WAKE_UP:
            # The QWaitCondition inside the SINGLE_SHOT_WAKE_UP '_do_work()'-
            # routine will likely have locked worker_DAQ. Hence, a
            # '_signal_stop_worker_DAQ' signal as above might not get handled by
            # worker_DAQ when emitted from out of this thread. Instead,
            # we directly call '_stop()' from out of this different thread,
            # which is perfectly fine for SINGLE_SHOT_WAKE_UP as per my design.
            self.worker_DAQ._stop()

        elif self.worker_DAQ._DAQ_trigger == DAQ_trigger.CONTINUOUS:
            # We directly call '_stop()' from out of this different thread,
            # which is perfectly fine for CONTINUOUS as per my design.
            self.worker_DAQ._stop()

        # Wait for worker_DAQ to confirm having stopped
        locker_wait = QtCore.QMutexLocker(self._mutex_wait_worker_DAQ)
        self._qwc_worker_DAQ_stopped.wait(self._mutex_wait_worker_DAQ)
        locker_wait.unlock()

        self._thread_DAQ.quit()
        print(
            "Closing thread %s "
            % "{:.<16}".format(self._thread_DAQ.objectName()),
            end="",
        )
        if self._thread_DAQ.wait(2000):
            print("done.\n", end="")
            return True
        else:
            print("FAILED.\n", end="")  # pragma: no cover
            return False  # pragma: no cover

    def quit_worker_send(self):
        """Stops ``worker_send`` and closes its thread.
        
        Returns:
            True if successful, False otherwise.
        """
        if self._thread_send is None or self.worker_send._started_okay is None:
            # CASE: quit() without create()
            #   _thread_DAQ == None
            #   _started_okay = None
            # CASE: quit() without start()
            #   _thread_DAQ == QThread()
            #   _started_okay = None
            return True

        # CASE: quit() with a device dead from the start
        #   _thread_DAQ == QThread()
        #   _started_okay = False

        # CASE: quit() with a device alive from the start
        #   _thread_DAQ == QThread()
        #   _started_okay = True

        if self.worker_send.DEBUG:
            tprint(
                "Worker_send %s: stop requested..." % self.dev.name, ANSI.WHITE,
            )

        # The QWaitCondition inside the SINGLE_SHOT_WAKE_UP '_do_work()'-
        # routine will likely have locked worker_DAQ. Hence, a
        # '_signal_stop_worker_DAQ' signal might not get handled by
        # worker_DAQ when emitted from out of this thread. Instead,
        # we directly call '_stop()' from out of this different thread,
        # which is perfectly fine as per my design.
        self.worker_send._stop()

        # Wait for worker_send to confirm having stopped
        locker_wait = QtCore.QMutexLocker(self._mutex_wait_worker_send)
        self._qwc_worker_send_stopped.wait(self._mutex_wait_worker_send)
        locker_wait.unlock()

        self._thread_send.quit()
        print(
            "Closing thread %s "
            % "{:.<16}".format(self._thread_send.objectName()),
            end="",
        )
        if self._thread_send.wait(2000):
            print("done.\n", end="")
            return True
        else:
            print("FAILED.\n", end="")  # pragma: no cover
            return False  # pragma: no cover

    def quit(self):
        """Stops all of any running workers and closes their respective threads.
        
        Returns:
            True if successful, False otherwise.
        """
        return self.quit_worker_DAQ() & self.quit_worker_send()

    # --------------------------------------------------------------------------
    #   worker_DAQ related
    # --------------------------------------------------------------------------

    @QtCore.pyqtSlot()
    def pause_DAQ(self):
        """Only useful in mode :obj:`DAQ_trigger.CONTINUOUS`. Requests
        ``worker_DAQ`` to pause and stop listening for data. After
        ``worker_DAQ`` has achieved the `paused` state, it will emit
        :obj:`signal_DAQ_paused`.
        
        This method can be called from another thread.
        """
        if self.worker_DAQ is not None:
            self.worker_DAQ.pause()

    @QtCore.pyqtSlot()
    def unpause_DAQ(self):
        """Only useful in mode :obj:`DAQ_trigger.CONTINUOUS`. Requests
        ``worker_DAQ`` to resume listening for data. After ``worker_DAQ`` has
        succesfully resumed, it will start emitting :obj:`signal_DAQ_updated`.
        
        This method can be called from another thread.
        """
        if self.worker_DAQ is not None:
            self.worker_DAQ.unpause()

    @QtCore.pyqtSlot()
    def wake_up_DAQ(self):
        """Only useful in mode :obj:`DAQ_trigger.SINGLE_SHOT_WAKE_UP`.
        
        This method can be called from another thread.
        """
        if self.worker_DAQ is not None:
            self.worker_DAQ.wake_up()

    # --------------------------------------------------------------------------
    #   worker_send related
    # --------------------------------------------------------------------------

    @QtCore.pyqtSlot()
    def send(self, instruction, pass_args=()):
        """Put an instruction on the worker_send queue and process the
         queue until empty.
         E.g. send(dev.write, "toggle LED")
         
         See 'Worker_send.add_to_queue()' for more details.
        """
        if self.worker_send is not None:
            self.worker_send.queued_instruction(instruction, pass_args)

    @QtCore.pyqtSlot()
    def add_to_send_queue(self, instruction, pass_args=()):
        """Put an instruction on the worker_send queue.
        E.g. add_to_send_queue(dev.write, "toggle LED")
        
        See 'Worker_send.add_to_queue()' for more details.
        """
        if self.worker_send is not None:
            self.worker_send.add_to_queue(instruction, pass_args)

    @QtCore.pyqtSlot()
    def process_send_queue(self):
        """Trigger processing the worker_send queue and send until empty.
        """
        if self.worker_send is not None:
            self.worker_send.process_queue()


# --------------------------------------------------------------------------
#   Worker_send
# --------------------------------------------------------------------------


class Worker_send(QtCore.QObject):
    """This worker maintains a thread-safe queue where desired device I/O
    operations, a.k.a. jobs, can be put onto. The worker will send out the
    operations to the device, first in first out (FIFO), until the queue is
    empty again.

    The worker will be placed inside a separate thread by its parent class
    QDeviceIO. 

    This worker uses the QWaitCondition mechanism. Hence, it will only send
    out all operations collected in the queue, whenever the thread it lives
    in is woken up by calling 'Worker_send.process_queue()'. When it has
    emptied the queue, the thread will go back to sleep again.

    No direct changes to the GUI should be performed inside this class.
    Instead, connect to the 'signal_send_updated' signal to instigate GUI
    changes when needed.

    Args:
        jobs_function (optional, default=None):
            Reference to an user-supplied function performing an alternative
            job handling when processing the worker_send queue. The default
            job handling effectuates calling 'func(*args)', where 'func' and
            'args' are retrieved from the worker_send queue, and nothing
            more. The default is sufficient when 'func' corresponds to an
            I/O operation that is an one-way send, i.e. a write operation
            without a reply.

            Instead of just write operations, you can also put a single or
            multiple query operation(s) in the queue and process each reply
            of the device accordingly. This is the purpose of this argument:
            To provide your own 'job processing routines' function. The
            function you supply must take two arguments, where the first
            argument will be 'func' and the second argument will be
            'args', which is a tuple. Both 'func' and 'args' will be
            retrieved from the worker_send queue and passed onto your
            own function.

            Example of a query operation by sending and checking for a
            special string value of 'func':

                def jobs_function(func, args):
                    if func == "query_id?":
                        # Query the device for its identity string
                        [success, ans_str] = self.dev.query("id?")
                        # And store the reply 'ans_str' in another variable
                        # at a higher scope or do stuff with it here.
                    else:
                        # Default job handling where, e.g.
                        # func = self.dev.write
                        # args = ("toggle LED",)
                        func(*args)

        DEBUG (bool, optional, default=False):
            Show debug info in terminal? Warning: Slow! Do not leave on
            unintentionally.

    Methods:
        add_to_queue(...):
            Put an instruction on the worker_send queue.

        process_queue():
            Trigger processing the worker_send queue until empty.

        queued_instruction(...):
            Put an instruction on the worker_send queue and process the
            queue until empty.
    """

    def __init__(
        self, *, qdev=None, jobs_function=None, DEBUG=False,
    ):
        super().__init__(None)
        self.DEBUG = DEBUG
        self.DEBUG_color = ANSI.YELLOW

        self.qdev = qdev
        self.dev = None if qdev is None else qdev.dev

        self.jobs_function = jobs_function
        self._started_okay = None

        self._running = True
        self._qwc = QtCore.QWaitCondition()
        self._mutex_wait = QtCore.QMutex()

        # Use a 'sentinel' value to signal the start and end of the queue
        # to ensure proper multithreaded operation.
        self._sentinel = None
        self._queue = queue.Queue()
        self._queue.put(self._sentinel)

        if self.DEBUG:
            tprint(
                "Worker_send %s: init @ thread %s"
                % (self.dev.name, _cur_thread_name()),
                self.DEBUG_color,
            )

    @_coverage_resolve_trace
    @QtCore.pyqtSlot()
    def _do_work(self):
        init = True

        def confirm_started(self):
            # Wait a tiny amount of extra time for QDeviceIO to have entered
            # 'self._qwc_worker_###_started.wait(self._mutex_wait_worker_###)'
            # of method 'start_worker_###()'.
            time.sleep(0.05)

            if self.DEBUG:
                tprint(
                    "Worker_send %s: start confirmed" % self.dev.name,
                    self.DEBUG_color,
                )

            # Send confirmation
            self.qdev._qwc_worker_send_started.wakeAll()

        if self.DEBUG:
            tprint(
                "Worker_send %s: starting @ thread %s"
                % (self.dev.name, _cur_thread_name()),
                self.DEBUG_color,
            )

        locker_wait = QtCore.QMutexLocker(self._mutex_wait)
        locker_wait.unlock()

        while self._running:
            locker_wait.relock()

            if self.DEBUG:
                tprint(
                    "Worker_send %s: waiting for wake trigger" % self.dev.name,
                    self.DEBUG_color,
                )

            if init:
                confirm_started(self)
                init = False

            self._qwc.wait(self._mutex_wait)

            if self.DEBUG:
                tprint(
                    "Worker_send %s: wake confirmed" % self.dev.name,
                    self.DEBUG_color,
                )

            # Needed check to prevent _perform_send() at final wake up
            # when _stop() has been called
            if self._running:
                self._perform_send()

            locker_wait.unlock()

        if self.DEBUG:
            tprint(
                "Worker_send %s: stop confirmed" % self.dev.name,
                self.DEBUG_color,
            )

        # Wait a tiny amount for the other thread to have entered the
        # QWaitCondition lock, before giving a wakingAll().
        QtCore.QTimer.singleShot(
            100, lambda: self.qdev._qwc_worker_send_stopped.wakeAll()
        )

    @_coverage_resolve_trace
    @QtCore.pyqtSlot()
    def _perform_send(self):
        if not self._started_okay:
            return

        locker = QtCore.QMutexLocker(self.dev.mutex)
        self.qdev.update_counter_send += 1

        if self.DEBUG:
            tprint(
                "Worker_send %s: lock   # %i"
                % (self.dev.name, self.qdev.update_counter_send),
                self.DEBUG_color,
            )

        """Process all jobs until the queue is empty. We must iterate 2
        times because we use a sentinel in a FIFO queue. First iter
        removes the old sentinel. Second iter processes the remaining
        queue items and will put back a new sentinel again.
        """
        for i in range(2):
            for job in iter(self._queue.get_nowait, self._sentinel):
                func = job[0]
                args = job[1:]

                if self.DEBUG:
                    if type(func) == str:
                        tprint(
                            "Worker_send %s: %s %s"
                            % (self.dev.name, func, args),
                            self.DEBUG_color,
                        )
                    else:
                        tprint(
                            "Worker_send %s: %s %s"
                            % (self.dev.name, func.__name__, args),
                            self.DEBUG_color,
                        )

                if self.jobs_function is None:
                    # Default job processing:
                    # Send I/O operation to the device
                    try:
                        func(*args)
                    except Exception as err:
                        pft(err)
                else:
                    # User-supplied job processing
                    self.jobs_function(func, args)

            # Put sentinel back in
            self._queue.put(self._sentinel)

        if self.DEBUG:
            tprint(
                "Worker_send %s: unlock # %i"
                % (self.dev.name, self.qdev.update_counter_send),
                self.DEBUG_color,
            )

        locker.unlock()
        self.qdev.signal_send_updated.emit()

    @QtCore.pyqtSlot()
    def _stop(self):
        """Stop the worker to prepare for quitting the worker thread
        """
        if self.DEBUG:
            tprint(
                "Worker_send %s: stopping" % self.dev.name, self.DEBUG_color,
            )

        self._running = False
        self._qwc.wakeAll()  # Wake up for the final time

    # ----------------------------------------------------------------------
    #   add_to_queue
    # ----------------------------------------------------------------------

    def add_to_queue(self, instruction, pass_args=()):
        """Put an instruction on the worker_send queue.
        E.g. add_to_queue(dev.write, "toggle LED")

        Args:
            instruction:
                Intended to be a reference to a device I/O function such as
                'self.dev.write'. However, you have the freedom to be
                creative and put e.g. strings decoding special instructions
                on the queue as well. Handling such special cases must be
                programmed by the user by supplying the argument
                'jobs_function', when instantiating
                'Worker_send', with your own job-processing-routines
                function. See 'Worker_send' for more details.

            pass_args (optional, default=()):
                Argument(s) to be passed to the instruction. Must be a
                tuple, but for convenience any other type will also be
                accepted if it concerns just a single argument that needs to
                be passed.
                
        NOTE: This method can be called from the MAIN/GUI thread all right.
        """
        if type(pass_args) is not tuple:
            pass_args = (pass_args,)
        self._queue.put((instruction, *pass_args))

    # ----------------------------------------------------------------------
    #   process_queue
    # ----------------------------------------------------------------------

    def process_queue(self):
        """Trigger processing the worker_send queue and send until empty.
        
        NOTE: This method can be called from the MAIN/GUI thread all right.
        """
        if self.DEBUG:
            tprint(
                "Worker_send %s: wake requested..." % self.dev.name, ANSI.WHITE,
            )

        self._qwc.wakeAll()

    # ----------------------------------------------------------------------
    #   queued_instruction
    # ----------------------------------------------------------------------

    def queued_instruction(self, instruction, pass_args=()):
        """Put an instruction on the worker_send queue and process the
        queue until empty. See 'add_to_queue()' for more details.
        E.g. queued_instruction(dev.write, "toggle LED")
        
        NOTE: This method can be called from the MAIN/GUI thread all right.
        """
        self.add_to_queue(instruction, pass_args)
        self.process_queue()


# --------------------------------------------------------------------------
#   Worker_DAQ
# --------------------------------------------------------------------------


class Worker_DAQ(QtCore.QObject):
    """This worker acquires data from the I/O device. It does so by calling
    a user-supplied function, passed as argument 'DAQ_function_to_run_each_
    update', containing your device I/O operations (and/or data parsing,
    processing or more), every iteration of the worker's event loop. 
    No direct changes to the GUI should be performed inside this function.
    Instead, connect to the 'signal_DAQ_updated' signal to instigate GUI
    changes when needed.

    The worker will be placed inside a separate thread by its parent class
    QDeviceIO. 

    The Worker_DAQ routine is robust in the following sense. It can be set
    to quit as soon as a communication error appears, or it could be set to
    allow a certain number of communication errors before it quits. The
    latter can be useful in non-critical implementations where continuity of
    the program is of more importance than preventing drops in data
    transmission. This, obviously, is a work-around for not having to tackle
    the source of the communication error, but sometimes you just need to
    struggle on. E.g., when your Arduino is out in the field and picks up
    occasional unwanted interference/ground noise that messes with your data
    transmission.

    Args:
        DAQ_interval_ms:
            TODO: Rewrite and explain different DAQ_trigger methods
            Desired data acquisition update interval in milliseconds.

        DAQ_function (optional, default=None):
            Reference to a user-supplied function containing the device
            query operations and subsequent data processing, to be invoked
            every DAQ update. It must return True when everything went
            successful, and False otherwise.

            NOTE: No direct changes to the GUI should run inside this
            function! If you do anyhow, expect a penalty in the timing
            stability of this worker.

            Example pseudo-code, where 'time' and 'temperature' are
            variables that live at a higher scope, presumably at main/GUI
            scope level:

            def my_update_function():
                # Query the device for its state. In this example we assume
                # the device replies with a time stamp and a temperature
                # reading. The function 'dev.query_temperature()' is also
                # supplied by the user and handles the direct communication
                # with the I/O device, returning..
                # BLABLABLA. TODO: rewrite and provide more clear example
                [success, reply] = dev.query_temperature()
                if not(success):
                    print("Device IOerror")
                    return False

                # Parse readings into separate variables and store them
                try:
                    [time, temperature] = parse(reply)
                except Exception as err:
                    print(err)
                    return False

                return True

        critical_not_alive_count (optional, default=1):
            The worker will allow for up to a certain number of consecutive
            communication failures with the device before hope is given up
            and a 'signal_connection_lost' signal is emitted. Use at your
            own discretion.

        DAQ_timer_type (PyQt5.QtCore.Qt.TimerType, optional, default=
                        PyQt5.QtCore.Qt.CoarseTimer):
            The update interval is timed to a QTimer running inside
            Worker_DAQ. The accuracy of the timer can be improved by setting
            it to PyQt5.QtCore.Qt.PreciseTimer with ~1 ms granularity, but
            it is resource heavy. Use sparingly.

        DAQ_trigger (optional, default=DAQ_trigger.INTERNAL_TIMER):
            TODO: write description

        DEBUG (bool, optional, default=False):
            Show debug info in terminal? Warning: Slow! Do not leave on
            unintentionally.
            
    Methods:
        pause():
            Only useful with DAQ_trigger.CONTINUOUS

        unpause():
            Only useful with DAQ_trigger.CONTINUOUS

        wake_up():
            Only useful with DAQ_trigger.SINGLE_SHOT_WAKE_UP
    """

    def __init__(
        self,
        *,
        qdev=None,
        DAQ_trigger=DAQ_trigger.INTERNAL_TIMER,
        DAQ_function=None,
        DAQ_interval_ms=1000,
        DAQ_timer_type=QtCore.Qt.CoarseTimer,
        critical_not_alive_count=1,
        calc_DAQ_rate_every_N_iter=25,  # TODO: set default value to 'auto' and implement further down. When integer, take over that value.
        DEBUG=False,
    ):
        super().__init__()
        self.DEBUG = DEBUG
        self.DEBUG_color = ANSI.CYAN

        self.qdev = qdev
        self.dev = None if qdev is None else qdev.dev

        self.DAQ_function = DAQ_function
        self.critical_not_alive_count = critical_not_alive_count
        self._DAQ_trigger = DAQ_trigger
        self._started_okay = None

        # Members specifically for INTERNAL_TIMER
        if self._DAQ_trigger == DAQ_trigger.INTERNAL_TIMER:
            self._DAQ_interval_ms = DAQ_interval_ms
            self._timer_type = DAQ_timer_type
            self._timer = None
            self.calc_DAQ_rate_every_N_iter = calc_DAQ_rate_every_N_iter
            # TODO: create a special value, like string 'auto_1_Hz' to
            # trigger below calculation
            # self.calc_DAQ_rate_every_N_iter = max(
            #        round(1e3/self._DAQ_interval_ms), 1)

        # Members specifically for SINGLE_SHOT_WAKE_UP
        elif self._DAQ_trigger == DAQ_trigger.SINGLE_SHOT_WAKE_UP:
            self._running = True
            self._qwc = QtCore.QWaitCondition()
            self._mutex_wait = QtCore.QMutex()
            self.calc_DAQ_rate_every_N_iter = calc_DAQ_rate_every_N_iter

        # Members specifically for CONTINUOUS
        # Note: At start-up, the worker will directly go into a paused state
        # and trigger a 'signal_DAQ_paused' PyQt signal
        elif self._DAQ_trigger == DAQ_trigger.CONTINUOUS:
            self._running = True
            self._pause = None  # Will be set at init of '_do_work()' when 'start_worker_DAQ()' is called
            self._paused = None  # Will be set at init of '_do_work()' when 'start_worker_DAQ()' is called
            self.calc_DAQ_rate_every_N_iter = calc_DAQ_rate_every_N_iter

        # QElapsedTimer (QET) to keep track of DAQ interval and DAQ rate
        self._QET_DAQ = QtCore.QElapsedTimer()
        self._QET_DAQ.start()
        self._prev_tick_DAQ_update = 0
        self._prev_tick_DAQ_rate = 0

        if self.DEBUG:
            tprint(
                "Worker_DAQ  %s: init @ thread %s"
                % (self.dev.name, _cur_thread_name()),
                self.DEBUG_color,
            )

    @_coverage_resolve_trace
    @QtCore.pyqtSlot()
    def _do_work(self):
        init = True

        def confirm_started(self):
            # Wait a tiny amount of extra time for QDeviceIO to have entered
            # 'self._qwc_worker_###_started.wait(self._mutex_wait_worker_###)'
            # of method 'start_worker_###()'.
            time.sleep(0.05)

            if self.DEBUG:
                tprint(
                    "Worker_DAQ  %s: start confirmed" % self.dev.name,
                    self.DEBUG_color,
                )

            # Send confirmation
            self.qdev._qwc_worker_DAQ_started.wakeAll()

        if self.DEBUG:
            tprint(
                "Worker_DAQ  %s: starting @ thread %s"
                % (self.dev.name, _cur_thread_name()),
                self.DEBUG_color,
            )

        # INTERNAL_TIMER
        if self._DAQ_trigger == DAQ_trigger.INTERNAL_TIMER:
            self._timer = QtCore.QTimer()
            self._timer.setInterval(self._DAQ_interval_ms)
            self._timer.timeout.connect(self._perform_DAQ)
            self._timer.setTimerType(self._timer_type)
            self._timer.start()
            confirm_started(self)

        # SINGLE_SHOT_WAKE_UP
        elif self._DAQ_trigger == DAQ_trigger.SINGLE_SHOT_WAKE_UP:
            locker_wait = QtCore.QMutexLocker(self._mutex_wait)
            locker_wait.unlock()

            while self._running:
                locker_wait.relock()

                if self.DEBUG:
                    tprint(
                        "Worker_DAQ  %s: waiting for wake trigger"
                        % self.dev.name,
                        self.DEBUG_color,
                    )

                if init:
                    confirm_started(self)
                    init = False

                self._qwc.wait(self._mutex_wait)

                if self.DEBUG:
                    tprint(
                        "Worker_DAQ  %s: wake confirmed" % self.dev.name,
                        self.DEBUG_color,
                    )

                # Needed check to prevent _perform_DAQ() at final wake up
                # when _stop() has been called
                if self._running:
                    self._perform_DAQ()

                locker_wait.unlock()

            if self.DEBUG:
                tprint(
                    "Worker_DAQ  %s: stop confirmed" % self.dev.name,
                    self.DEBUG_color,
                )

            # Wait a tiny amount for the other thread to have entered the
            # QWaitCondition lock, before giving a wakingAll().
            QtCore.QTimer.singleShot(
                100, lambda: self.qdev._qwc_worker_DAQ_stopped.wakeAll()
            )

        # CONTINUOUS
        elif self._DAQ_trigger == DAQ_trigger.CONTINUOUS:
            while self._running:
                if init:
                    self._pause = True
                    self._paused = True

                    if self.DEBUG:
                        tprint(
                            "Worker_DAQ  %s: starting up paused"
                            % self.dev.name,
                            self.DEBUG_color,
                        )

                    self.qdev.signal_DAQ_paused.emit()

                    confirm_started(self)
                    init = False

                if self._pause:  # == True
                    if self._pause != self._paused:
                        if self.DEBUG and not init:
                            tprint(
                                "Worker_DAQ  %s: pause confirmed"
                                % self.dev.name,
                                self.DEBUG_color,
                            )
                        self.qdev.signal_DAQ_paused.emit()
                        self._paused = True

                    time.sleep(0.01)  # Do not hog the CPU while paused

                else:  # == False
                    if self._pause != self._paused:
                        if self.DEBUG:
                            tprint(
                                "Worker_DAQ  %s: unpause confirmed"
                                % self.dev.name,
                                self.DEBUG_color,
                            )
                        self._paused = False

                    self._perform_DAQ()

            if self.DEBUG:
                tprint(
                    "Worker_DAQ  %s: stop confirmed" % self.dev.name,
                    self.DEBUG_color,
                )

            # Wait a tiny amount for 'create_worker_DAQ()', which is running
            # in a different thread than this one, to have entered the
            # QWaitCondition lock, before giving a wakingAll().
            QtCore.QTimer.singleShot(
                100, lambda: self.qdev._qwc_worker_DAQ_stopped.wakeAll()
            )

    @_coverage_resolve_trace
    @QtCore.pyqtSlot()
    def _perform_DAQ(self):
        if not self._started_okay:
            return

        locker = QtCore.QMutexLocker(self.dev.mutex)
        self.qdev.update_counter_DAQ += 1

        if self.DEBUG:
            tprint(
                "Worker_DAQ  %s: lock   # %i"
                % (self.dev.name, self.qdev.update_counter_DAQ),
                self.DEBUG_color,
            )

        # Keep track of the obtained DAQ update interval
        now = self._QET_DAQ.elapsed()
        if self.qdev.update_counter_DAQ > 1:
            self.qdev.obtained_DAQ_interval_ms = (
                now - self._prev_tick_DAQ_update
            )
        self._prev_tick_DAQ_update = now

        # Keep track of the obtained DAQ rate
        if self.qdev.update_counter_DAQ % self.calc_DAQ_rate_every_N_iter == 0:
            try:
                self.qdev.obtained_DAQ_rate_Hz = (
                    self.calc_DAQ_rate_every_N_iter
                    / (now - self._prev_tick_DAQ_rate)
                    * 1e3
                )
            except ZeroDivisionError:  # pragma: no cover
                self.qdev.obtained_DAQ_rate_Hz = np.nan  # pragma: no cover
            self._prev_tick_DAQ_rate = now

        # Check the not alive counter
        if self.qdev.not_alive_counter_DAQ >= self.critical_not_alive_count:
            dprint(
                "\nWorker_DAQ %s: Lost connection to device.\n" % self.dev.name,
                ANSI.RED,
            )
            self.dev.is_alive = False

            locker.unlock()
            self._stop()
            # self.qdev.signal_DAQ_updated.emit()  # TODO: Was uncommented in the prototype version. Check if we can safely remove this line.
            self.qdev.signal_connection_lost.emit()
            return

        # ----------------------------------
        #   User-supplied DAQ function
        # ----------------------------------

        if not self.DAQ_function is None:
            if self.DAQ_function():
                # Did return True, hence was succesfull
                # --> Reset the 'not alive' counter
                self.qdev.not_alive_counter_DAQ = 0
            else:
                # Did return False, hence was unsuccesfull
                self.qdev.not_alive_counter_DAQ += 1

        # ----------------------------------
        #   End user-supplied DAQ function
        # ----------------------------------

        if self.DEBUG:
            tprint(
                "Worker_DAQ  %s: unlock # %i"
                % (self.dev.name, self.qdev.update_counter_DAQ),
                self.DEBUG_color,
            )

        locker.unlock()
        self.qdev.signal_DAQ_updated.emit()

    @QtCore.pyqtSlot()
    def _stop(self):
        """Stop the worker to prepare for quitting the worker thread.
        """
        if self.DEBUG:
            tprint("Worker_DAQ  %s: stopping" % self.dev.name, self.DEBUG_color)

        if self._DAQ_trigger == DAQ_trigger.INTERNAL_TIMER:
            # NOTE: The timer /must/ be stopped from the worker_DAQ thread!
            self._timer.stop()

            if self.DEBUG:
                tprint(
                    "Worker_DAQ  %s: stop confirmed" % self.dev.name,
                    self.DEBUG_color,
                )

            # Wait a tiny amount for the other thread to have entered the
            # QWaitCondition lock, before giving a wakingAll().
            QtCore.QTimer.singleShot(
                100, lambda: self.qdev._qwc_worker_DAQ_stopped.wakeAll()
            )

        elif self._DAQ_trigger == DAQ_trigger.SINGLE_SHOT_WAKE_UP:
            self._running = False
            self._qwc.wakeAll()  # Wake up for the final time

        elif self._DAQ_trigger == DAQ_trigger.CONTINUOUS:
            self._running = False

    # ----------------------------------------------------------------------
    #   pause / unpause
    # ----------------------------------------------------------------------

    @QtCore.pyqtSlot()
    def pause(self):
        """Only useful with DAQ_trigger.CONTINUOUS
        NOTE: This method can be called from the MAIN/GUI thread all right.
        """
        if self._DAQ_trigger == DAQ_trigger.CONTINUOUS:
            if self.DEBUG:
                tprint(
                    "Worker_DAQ  %s: pause requested..." % self.dev.name,
                    ANSI.WHITE,
                )

            # The possible undefined behavior of changing variable '_pause'
            # from out of another thread gets handled acceptably correct in
            # '_do_work()' as per my design.
            self._pause = True

    @QtCore.pyqtSlot()
    def unpause(self):
        """Only useful with DAQ_trigger.CONTINUOUS
        NOTE: This method can be called from the MAIN/GUI thread all right.
        """
        if self._DAQ_trigger == DAQ_trigger.CONTINUOUS:
            if self.DEBUG:
                tprint(
                    "Worker_DAQ  %s: unpause requested..." % self.dev.name,
                    ANSI.WHITE,
                )

            # The possible undefined behavior of changing variable '_pause'
            # from out of another thread gets handled acceptably correct in
            # '_do_work()' as per my design.
            self._pause = False

    # ----------------------------------------------------------------------
    #   wake_up
    # ----------------------------------------------------------------------

    @QtCore.pyqtSlot()
    def wake_up(self):
        """Only useful with DAQ_trigger.SINGLE_SHOT_WAKE_UP
        NOTE: This method can be called from the MAIN/GUI thread all right.
        """
        if self._DAQ_trigger == DAQ_trigger.SINGLE_SHOT_WAKE_UP:
            if self.DEBUG:
                tprint(
                    "Worker_DAQ  %s: wake requested..." % self.dev.name,
                    ANSI.WHITE,
                )

            self._qwc.wakeAll()
