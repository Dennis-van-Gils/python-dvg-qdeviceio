#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt5 module containing the framework for multithreaded communication and
periodical data acquisition for an I/O device.

MAIN CONTENTS:
--------------

    Class:
        QDeviceIO(...)
            Methods:
                attach_device(...)
                
                create_worker_DAQ(...)
                create_worker_send(...)
                
                start_worker_DAQ(...)
                start_worker_send(...)
                
                quit_worker_DAQ()
                quit_worker_send()
                quit_all_workers()

            Inner-class instances:
                worker_DAQ(...)
                    Methods:
                        wake_up(...)
                        schedule_suspend(...)

                worker_send(...):
                    Methods:
                        add_to_queue(...)
                        process_queue()
                        queued_instruction(...)

            Main data attributes:
                DAQ_update_counter
                obtained_DAQ_update_interval_ms
                obtained_DAQ_rate_Hz

            Signals:
                signal_DAQ_updated()
                signal_DAQ_suspended()
                signal_connection_lost()
"""
__author__      = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__         = "https://github.com/Dennis-van-Gils/python-dvg-qdeviceio"
__date__        = "30-05-2020"
__version__     = "0.0.1"   # This DvG_QDeviceIO.py v0.0.1 on PyPI is based on the pre-PyPI prototype DvG_dev_Base__pyqt_lib.py v1.3.3

from enum import IntEnum, unique
import queue
import time as Time

# Code coverage tools 'coverage' and 'pytest-cov' don't seem to correctly trace 
# code which is inside methods called from within QThreads, see
# https://github.com/nedbat/coveragepy/issues/686
# To mitigate this problem, I use a custom decorator '@coverage_resolve_trace' 
# to be hung onto those method definitions. This will prepend the decorated
# method code with 'sys.settrace(threading._trace_hook)' when a code
# coverage test is detected. When no coverage test is detected, it will just
# pass the original method untouched.
import sys
import threading
from functools import wraps

running_coverage = 'coverage' in sys.modules
if running_coverage: print("\nCode coverage test detected\n")

def coverage_resolve_trace(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if running_coverage: sys.settrace(threading._trace_hook)
        fn(*args, **kwargs)
    return wrapped    

import numpy as np
from PyQt5 import QtCore
from DvG_debug_functions import ANSI, dprint, print_fancy_traceback as pft

# Short-hand alias for DEBUG information
def cur_thread_name(): return QtCore.QThread.currentThread().objectName()

@unique
class DAQ_trigger(IntEnum):
    [INTERNAL_TIMER, SINGLE_SHOT_WAKE_UP, CONTINUOUS] = range(3)

# ------------------------------------------------------------------------------
#   InnerClassDescriptor
# ------------------------------------------------------------------------------

class InnerClassDescriptor(object):
    """Allows an inner class instance to get the attributes from the outer class
    instance by referring to 'self.outer'. Used in this module by the
    'Worker_DAQ' and 'Worker_send' classes. Usage: @InnerClassDescriptor.
    Not to be used outside of this module.
    """
    def __init__(self, cls):
        self.cls = cls

    def __get__(self, instance, outerclass):
        class Wrapper(self.cls):
            outer = instance
        Wrapper.__name__ = self.cls.__name__
        return Wrapper

# ------------------------------------------------------------------------------
#   QDeviceIO
# ------------------------------------------------------------------------------

class QDeviceIO(QtCore.QObject):
    """This class provides the base framework for multithreaded communication
    and periodical data acquisition for an I/O device.

    All device I/O operations will be offloaded to 'workers', each running in
    a newly created thread instead of in the main/GUI thread.

        - Worker_DAQ:
            Periodically acquires data from the device.

        - Worker_send:
            Maintains a thread-safe queue where desired device I/O operations
            can be put onto, and sends the queued operations first in first out
            (FIFO) to the device.

    This class can be mixed into your own specific device I/O class definition.
    Hint: Look up 'mixin class' for Python.
    E.g., when writing your own device I/O library for an Arduino:
        class QDevIO_Arduino(DvG_QDeviceIO.QDeviceIO, QtCore.QObject):

    Methods:
        attach_device(...)
            Attach a reference to a 'device' instance with I/O methods.

        create_worker_DAQ():
            Create a single instance of 'Worker_DAQ' and transfer it to a
            separate (PyQt5.QtCore.QThread) thread called '_thread_DAQ'.

        create_worker_send():
            Create a single instance of 'Worker_send' and transfer it to a
            separate (PyQt5.QtCore.QThread) thread called '_thread_send'.

        start_worker_DAQ(...):
            Start running the event loop of the 'worker_DAQ' thread.
            I.e., start acquiring data periodically from the device.

        start_worker_send(...):
            Start running the event loop of the 'worker_send' thread.
            I.e., start maintaining the desired device I/O operations queue.

        quit_worker_DAQ():
            Stop 'worker_DAQ' and close its thread.

        quit_worker_send()
            Stop 'worker_send' and close its thread.

        quit_all_workers():
            Stop all of any running workers and close their respective threads.
            Safer and more convenient than calling 'quit_worker_DAQ' and
            'quit_worker_send', individually.

    Inner-class instances:
        worker_DAQ
        worker_send

    Main data attributes:
        dev:
            Reference to a 'device' instance with I/O methods. Needs to be set
            by calling 'attach_device(...)'.

        dev.mutex (PyQt5.QtCore.QMutex):
            Mutex to allow for properly multithreaded device I/O operations.

        DAQ_update_counter:
            Increments every time 'worker_DAQ' updates.

        obtained_DAQ_update_interval_ms:
            Obtained time interval in milliseconds since the previous
            'worker_DAQ' update.

        obtained_DAQ_rate_Hz:
            Obtained acquisition rate of 'worker_DAQ' in Hertz, evaluated every
            second.

    Signals:
        signal_DAQ_updated:
            Emitted by 'worker_DAQ' when '_perform_DAQ' has finished.

        signal_connection_lost:
            Indicates that we lost connection to the device, because one or more
            device I/O operations failed. Emitted by 'worker_DAQ' during
            '_perform_DAQ' when 'DAQ_not_alive_counter' is equal to or larger
            than 'worker_DAQ.critical_not_alive_count'.
    """
    signal_DAQ_updated     = QtCore.pyqtSignal()
    signal_DAQ_suspended   = QtCore.pyqtSignal()
    signal_connection_lost = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super(QDeviceIO, self).__init__(parent=parent)

        self.dev = self.NoAttachedDevice()
        
        self.worker_DAQ  = None
        self.worker_send = None
        
        self._thread_DAQ  = None
        self._thread_send = None

        self.DAQ_update_counter = 0
        self.DAQ_not_alive_counter = 0

        self.obtained_DAQ_update_interval_ms = np.nan
        self.obtained_DAQ_rate_Hz = np.nan

    class NoAttachedDevice():
        name = "NoAttachedDevice"
        mutex = QtCore.QMutex()
        is_alive = False

    # --------------------------------------------------------------------------
    #   attach_device
    # --------------------------------------------------------------------------

    def attach_device(self, dev):
        """Attach a reference to a 'device' instance with I/O methods.
        
        Returns True when successful, False otherwise.
        """
        if type(self.dev) == self.NoAttachedDevice:
            self.dev = dev
            #TODO: Test for existence required members
            # dev.name, dev.mutex, dev.is_alive
            return True
        else:
            pft("Device can be attached only once. Already attached to '%s'." %
                self.dev.name)
            return False

    # --------------------------------------------------------------------------
    #   Create workers
    # --------------------------------------------------------------------------

    def create_worker_DAQ(self, **kwargs):
        """Create a single instance of 'Worker_DAQ' and transfer it to 
        the separate (PyQt5.QtCore.QThread) thread '_thread_DAQ'.

        Args:
            **kwargs
                Will be passed directly onto Worker_DAQ.__init__()
        """
        self.worker_DAQ = self.Worker_DAQ(**kwargs)            
        self._thread_DAQ = QtCore.QThread()
        self._thread_DAQ.setObjectName("%s_DAQ" % self.dev.name)            
        self.worker_DAQ.moveToThread(self._thread_DAQ)            
        self._thread_DAQ.started.connect(self.worker_DAQ._do_work)
            
    def create_worker_send(self, **kwargs):
        """Create a single instance of 'Worker_send' and transfer it to 
        the separate (PyQt5.QtCore.QThread) thread '_thread_send'.

        Args:
            **kwargs
                Will be passed directly onto Worker_send.__init__()
        """
        self.worker_send = self.Worker_send(**kwargs)
        self._thread_send = QtCore.QThread()
        self._thread_send.setObjectName("%s_send" % self.dev.name)
        self.worker_send.moveToThread(self._thread_send)
        self._thread_send.started.connect(self.worker_send._do_work)
        
    # --------------------------------------------------------------------------
    #   Start workers
    # --------------------------------------------------------------------------

    def start_worker_DAQ(self, priority=QtCore.QThread.InheritPriority):
        """Start running the event loop of the worker thread.

        Args:
            priority (PyQt5.QtCore.QThread.Priority, optional, default=
                      QtCore.QThread.InheritPriority):
                By default, the 'worker_DAQ' thread runs in the operating system
                at the same thread priority as the main/GUI thread. You can
                change to higher priority by setting 'priority' to, e.g.,
                'QtCore.QThread.TimeCriticalPriority'. Be aware that this is
                resource heavy, so use sparingly.

        Returns True when successful, False otherwise.
        """
        if self._thread_DAQ is None:
            pft("Worker_DAQ %s: Can't start thread because it does not exist. "
                "Did you forget to call 'create_worker_DAQ' first?" %
                self.dev.name)
            return False
        
        if not self.dev.is_alive:
            print("Worker_DAQ %s: Can't start thread because device is not "
                  "alive." % self.dev.name)
            return False

        self._thread_DAQ.start(priority)
        return True

    def start_worker_send(self, priority=QtCore.QThread.InheritPriority):
        """Start running the event loop of the worker thread.

        Args:
            priority (PyQt5.QtCore.QThread.Priority, optional, default=
                      QtCore.QThread.InheritPriority):
                By default, the 'worker_send' thread runs in the operating system
                at the same thread priority as the main/GUI thread. You can
                change to higher priority by setting 'priority' to, e.g.,
                'QtCore.QThread.TimeCriticalPriority'. Be aware that this is
                resource heavy, so use sparingly.

        Returns True when successful, False otherwise.
        """
        if self._thread_send is None:
            pft("Worker_send %s: Can't start thread because it does not exist. "
                "Did you forget to call 'create_worker_send' first?" %
                self.dev.name)
            return False
        
        if not self.dev.is_alive:
            print("Worker_send %s: Can't start thread because device is not "
                  "alive." % self.dev.name)
            return False

        self._thread_send.start(priority)
        return True

    # --------------------------------------------------------------------------
    #   Quit workers
    # --------------------------------------------------------------------------

    def quit_worker_DAQ(self):
        """Stop 'worker_DAQ' and close its thread.
        
        Returns True when successful, False otherwise.
        """
        if self._thread_DAQ is not None:
            self.worker_DAQ._stop()
            self._thread_DAQ.quit()
            print("Closing thread %s " %
                  "{:.<16}".format(self._thread_DAQ.objectName()), end='')
            if self._thread_DAQ.wait(2000):
                print("done.\n", end='')
                return True
            else:
                print("FAILED.\n", end='')      # pragma: no cover
                return False                    # pragma: no cover
            
        else: return True

    def quit_worker_send(self):
        """Stop 'worker_send' and close its thread.
        
        Returns True when successful, False otherwise.
        """
        if self._thread_send is not None:
            self.worker_send._stop()
            self._thread_send.quit()
            print("Closing thread %s " %
                  "{:.<16}".format(self._thread_send.objectName()), end='')
            if self._thread_send.wait(2000):
                print("done.\n", end='')
                return True
            else:
                print("FAILED.\n", end='')      # pragma: no cover
                return False                    # pragma: no cover
            
        else: return True

    def quit_all_workers(self):
        """Stop all of any running workers and close their respective threads.
        
        Returns True when successful, False otherwise.
        """
        return (self.quit_worker_DAQ() & self.quit_worker_send())

    # --------------------------------------------------------------------------
    #   Worker_DAQ
    # --------------------------------------------------------------------------

    @InnerClassDescriptor
    class Worker_DAQ(QtCore.QObject):
        """This worker acquires data from the device. It does so by calling a
        user-supplied function containing your device I/O operations (and/or
        data parsing, processing or more), every iteration of the worker's event
        loop (i.e. _perform_DAQ()).

        The worker should be placed inside a separate thread. No direct changes
        to the GUI should be performed inside this class. If needed, use the
        QtCore.pyqtSignal() mechanism to instigate GUI changes.

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
            DAQ_update_interval_ms:
                Desired data acquisition update interval in milliseconds.

            DAQ_function_to_run_each_update (optional, default=None):
                Reference to a user-supplied function containing the device
                query operations and subsequent data processing, to be invoked
                every DAQ update. It should return True when everything went
                successful, and False otherwise.

                NOTE: No direct changes to the GUI should run inside this
                function! If you do anyhow, expect a penalty in the timing
                stability of this worker.

                E.g. pseudo-code, where 'time' and 'reading_1' are variables
                that live at a higher scope, presumably at main/GUI scope level.

                def my_update_function():
                    # Query the device for its state
                    [success, tmp_state] = dev.query_ascii_values("state?")
                    if not(success):
                        print("Device IOerror")
                        return False

                    # Parse readings into separate variables
                    try:
                        [time, reading_1] = tmp_state
                    except Exception as err:
                        print(err)
                        return False

                    return True

            DAQ_critical_not_alive_count (optional, default=1):
                The worker will allow for up to a certain number of
                communication failures with the device before hope is given up
                and a 'connection lost' signal is emitted. Use at your own
                discretion.

            DAQ_timer_type (PyQt5.QtCore.Qt.TimerType, optional, default=
                            PyQt5.QtCore.Qt.CoarseTimer):
                The update interval is timed to a QTimer running inside
                Worker_DAQ. The accuracy of the timer can be improved by setting
                it to PyQt5.QtCore.Qt.PreciseTimer with ~1 ms granularity, but
                it is resource heavy. Use sparingly.

            DAQ_trigger_by (optional, default=DAQ_trigger.INTERNAL_TIMER):
                TO DO: write description

            DEBUG (bool, optional, default=False):
                Show debug info in terminal? Warning: Slow! Do not leave on
                unintentionally.
        """
        def __init__(self, *,
                     DAQ_trigger_by=DAQ_trigger.INTERNAL_TIMER,
                     DAQ_function_to_run_each_update=None,
                     DAQ_update_interval_ms=1000,
                     DAQ_timer_type=QtCore.Qt.CoarseTimer,                     
                     DAQ_critical_not_alive_count=1,
                     calc_DAQ_rate_every_N_iter=25, # TODO: set default value to 'auto' and implement further down. When integer, take over that value.
                     DEBUG=False):
            super().__init__(None)
            self.DEBUG = DEBUG
            self.DEBUG_color = ANSI.CYAN

            self.dev = self.outer.dev
            self.trigger_by = DAQ_trigger_by
            self.function_to_run_each_update = DAQ_function_to_run_each_update
            self.critical_not_alive_count = DAQ_critical_not_alive_count
            
            # Members specifically for INTERNAL_TIMER
            if self.trigger_by == DAQ_trigger.INTERNAL_TIMER:
                self.update_interval_ms = DAQ_update_interval_ms
                self.timer_type = DAQ_timer_type
                self.calc_DAQ_rate_every_N_iter = calc_DAQ_rate_every_N_iter
                # TODO: create a special value, like string 'auto_1_Hz' to
                # trigger below calculation
                #self.calc_DAQ_rate_every_N_iter = max(
                #        round(1e3/self.update_interval_ms), 1)
            
            # Members specifically for SINGLE_SHOT_WAKE_UP
            elif self.trigger_by == DAQ_trigger.SINGLE_SHOT_WAKE_UP:
                self.running = True
                self.qwc = QtCore.QWaitCondition()
                self.mutex_wait = QtCore.QMutex()
                self.calc_DAQ_rate_every_N_iter = calc_DAQ_rate_every_N_iter
            
            # Members specifically for CONTINUOUS
            elif self.trigger_by == DAQ_trigger.CONTINUOUS:
                self.running = True
                self.suspend = True    # Start with the worker suspended and
                self.suspended = False # immediately trigger 'signal_DAQ_suspended'
                self.calc_DAQ_rate_every_N_iter = calc_DAQ_rate_every_N_iter
                
            # QElapsedTimer (QET) to keep track of DAQ interval and DAQ rate
            self.QET_DAQ = QtCore.QElapsedTimer()
            self.QET_DAQ.start()
            self.prev_tick_DAQ_update = 0
            self.prev_tick_DAQ_rate = 0

            if self.DEBUG:
                dprint("Worker_DAQ  %s: init @ thread %s" %
                       (self.dev.name, cur_thread_name()), self.DEBUG_color)

        @coverage_resolve_trace
        @QtCore.pyqtSlot()
        def _do_work(self):  
            if self.DEBUG:
                dprint("Worker_DAQ  %s: work @ thread %s" %
                       (self.dev.name, cur_thread_name()), self.DEBUG_color)

            # INTERNAL_TIMER
            if self.trigger_by == DAQ_trigger.INTERNAL_TIMER:
                self.timer = QtCore.QTimer()
                self.timer.setInterval(self.update_interval_ms)
                self.timer.timeout.connect(self._perform_DAQ)
                self.timer.setTimerType(self.timer_type)
                self.timer.start()

            # SINGLE_SHOT_WAKE_UP
            elif self.trigger_by == DAQ_trigger.SINGLE_SHOT_WAKE_UP:
                while self.running:
                    locker_wait = QtCore.QMutexLocker(self.mutex_wait)

                    if self.DEBUG:
                        dprint("Worker_DAQ  %s: waiting for trigger" %
                               self.dev.name, self.DEBUG_color)

                    self.qwc.wait(self.mutex_wait)
                    self._perform_DAQ()

                    locker_wait.unlock()

                if self.DEBUG:
                    dprint("Worker_DAQ  %s: done running" % self.dev.name,
                           self.DEBUG_color)
            
            # CONTINUOUS
            elif self.trigger_by == DAQ_trigger.CONTINUOUS:
                while self.running:
                    if self.suspend:
                        if (self.suspend != self.suspended):
                            if self.DEBUG:
                                dprint("Worker_DAQ  %s: suspended" % 
                                       self.dev.name, self.DEBUG_color)
                            self.outer.signal_DAQ_suspended.emit()
                        
                        self.suspended = True
                        Time.sleep(0.01)  # Do not hog the CPU while suspended
                        pass
                    else:
                        self.suspended = False
                        self._perform_DAQ()
                        
                if self.DEBUG:
                    dprint("Worker_DAQ  %s: done running" % self.dev.name,
                           self.DEBUG_color)

        @coverage_resolve_trace
        @QtCore.pyqtSlot()
        def _perform_DAQ(self):            
            locker = QtCore.QMutexLocker(self.dev.mutex)
            self.outer.DAQ_update_counter += 1

            if self.DEBUG:
                dprint("Worker_DAQ  %s: lock   # %i" %
                       (self.dev.name, self.outer.DAQ_update_counter),
                       self.DEBUG_color)

            # Keep track of the obtained DAQ update interval
            now = self.QET_DAQ.elapsed()
            if self.outer.DAQ_update_counter > 1:
                self.outer.obtained_DAQ_update_interval_ms = (
                        now - self.prev_tick_DAQ_update)
            self.prev_tick_DAQ_update = now

            # Keep track of the obtained DAQ rate
            if (self.outer.DAQ_update_counter %
                self.calc_DAQ_rate_every_N_iter == 0):
                try:
                    self.outer.obtained_DAQ_rate_Hz = (
                            self.calc_DAQ_rate_every_N_iter /
                            (now - self.prev_tick_DAQ_rate) * 1e3)
                except ZeroDivisionError:                     # pragma: no cover
                    self.outer.obtained_DAQ_rate_Hz = np.nan  # pragma: no cover
                self.prev_tick_DAQ_rate = now

            # Check the not alive counter
            if (self.outer.DAQ_not_alive_counter >=
                self.critical_not_alive_count):
                dprint("\nWorker_DAQ %s: Determined device is not alive "
                       "anymore." % self.dev.name)
                self.dev.is_alive = False

                locker.unlock()
                self._stop()
                self.outer.signal_DAQ_updated.emit()
                self.outer.signal_connection_lost.emit()
                return

            # ----------------------------------
            #   User-supplied DAQ function
            # ----------------------------------

            if not(self.function_to_run_each_update is None):
                if self.function_to_run_each_update():
                    # Did return True, hence was succesfull
                    self.outer.DAQ_not_alive_counter = 0
                else:
                    # Did return False, hence was unsuccesfull
                    self.outer.DAQ_not_alive_counter += 1

            # ----------------------------------
            #   End user-supplied DAQ function
            # ----------------------------------

            if self.DEBUG:
                dprint("Worker_DAQ  %s: unlock # %i" % 
                       (self.dev.name, self.outer.DAQ_update_counter),
                       self.DEBUG_color)

            locker.unlock()
            self.outer.signal_DAQ_updated.emit()
        
        @QtCore.pyqtSlot()
        def _stop(self):
            """Stop the worker to prepare for quitting the worker thread
            """
            if self.trigger_by == DAQ_trigger.INTERNAL_TIMER:
                if hasattr(self, 'timer'):
                    #self.timer.stop()  # Leave commented out
                    # You should not stop a timer from out of another thread!
                    # Quitting the thread will take care of stopping the timer
                    pass
            
            elif self.trigger_by == DAQ_trigger.SINGLE_SHOT_WAKE_UP:
                self.running = False
                if hasattr(self, 'qwc'):
                    self.qwc.wakeAll()
                
            elif self.trigger_by == DAQ_trigger.CONTINUOUS:
                self.running = False
                
        @QtCore.pyqtSlot(bool)
        def schedule_suspend(self, state=True):
            """Only useful with DAQ_trigger.CONTINUOUS
            TODO: change names schedule_suspend, suspend and suspended to
            something more clear
            """
            if self.trigger_by == DAQ_trigger.CONTINUOUS:
                self.suspend = state
                
                if self.DEBUG:
                    dprint("Worker_DAQ  %s: schedule suspend=%s" % 
                           (self.dev.name, state), self.DEBUG_color)
                        
        # ----------------------------------------------------------------------
        #   wake_up
        # ----------------------------------------------------------------------

        def wake_up(self):
            """Only useful with DAQ_trigger.SINGLE_SHOT_WAKE_UP
            """
            if self.trigger_by == DAQ_trigger.SINGLE_SHOT_WAKE_UP:
                self.qwc.wakeAll()

    # --------------------------------------------------------------------------
    #   Worker_send
    # --------------------------------------------------------------------------

    @InnerClassDescriptor
    class Worker_send(QtCore.QObject):
        """This worker maintains a thread-safe queue where desired device I/O
        operations, a.k.a. jobs, can be put onto. The worker will send out the
        operations to the device, first in first out (FIFO), until the queue is
        empty again.

        The worker should be placed inside a separate thread. This worker uses
        the QWaitCondition mechanism. Hence, it will only send out all
        operations collected in the queue, whenever the thread it lives in is
        woken up by calling 'Worker_send.process_queue()'. When it has emptied
        the queue, the thread will go back to sleep again.

        No direct changes to the GUI should be performed inside this class. If
        needed, use the QtCore.pyqtSignal() mechanism to instigate GUI changes.

        Args:
            alt_process_jobs_function (optional, default=None):
                Reference to an user-supplied function performing an alternative
                job handling when processing the worker_send queue. The default
                job handling effectuates calling 'func(*args)', where 'func' and
                'args' are retrieved from the worker_send queue, and nothing
                more. The default is sufficient when 'func' corresponds to an
                I/O operation that is an one-way send, i.e. a write operation
                without a reply.

                Instead of just write operations, you can also put query
                operations in the queue and process each reply of the device
                accordingly. This is the purpose of this argument: To provide
                your own 'job processing routines' function. The function you
                supply must take two arguments, where the first argument will be
                'func' and the second argument will be 'args', which is a tuple.
                Both 'func' and 'args' will be retrieved from the worker_send
                queue and passed onto your own function.

                Example of a query operation by sending and checking for a
                special string value of 'func':

                    def my_alt_process_jobs_function(func, args):
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
                Trigger processing the worker_send queue.

            queued_instruction(...):
                Put an instruction on the worker_send queue and process the
                queue.
        """

        def __init__(self, *,
                     alt_process_jobs_function=None,
                     DEBUG=False):
            super().__init__(None)
            self.DEBUG = DEBUG
            self.DEBUG_color = ANSI.YELLOW

            self.dev = self.outer.dev
            self.alt_process_jobs_function = alt_process_jobs_function

            self.update_counter = 0
            self.qwc = QtCore.QWaitCondition()
            self.mutex_wait = QtCore.QMutex()
            self.running = True

            # Use a 'sentinel' value to signal the start and end of the queue
            # to ensure proper multithreaded operation.
            self.sentinel = None
            self.queue = queue.Queue()
            self.queue.put(self.sentinel)

            if self.DEBUG:
                dprint("Worker_send %s: init @ thread %s" %
                       (self.dev.name, cur_thread_name()), self.DEBUG_color)

        @coverage_resolve_trace
        @QtCore.pyqtSlot()
        def _do_work(self):
            if self.DEBUG:
                dprint("Worker_send %s: work @ thread %s" %
                       (self.dev.name, cur_thread_name()), self.DEBUG_color)

            while self.running:
                locker_wait = QtCore.QMutexLocker(self.mutex_wait)

                if self.DEBUG:
                    dprint("Worker_send %s: waiting for trigger" %
                           self.dev.name, self.DEBUG_color)

                self.qwc.wait(self.mutex_wait)
                locker = QtCore.QMutexLocker(self.dev.mutex)
                self.update_counter += 1

                if self.DEBUG:
                    dprint("Worker_send %s: lock   # %i" %
                           (self.dev.name, self.update_counter),
                           self.DEBUG_color)

                """Process all jobs until the queue is empty. We must iterate 2
                times because we use a sentinel in a FIFO queue. First iter
                removes the old sentinel. Second iter processes the remaining
                queue items and will put back a new sentinel again.
                """
                for i in range(2):
                    for job in iter(self.queue.get_nowait, self.sentinel):
                        func = job[0]
                        args = job[1:]

                        if self.DEBUG:
                            if type(func) == str:
                                dprint("Worker_send %s: %s %s" %
                                       (self.dev.name, func, args),
                                       self.DEBUG_color)
                            else:
                                dprint("Worker_send %s: %s %s" %
                                       (self.dev.name, func.__name__, args),
                                       self.DEBUG_color)

                        if self.alt_process_jobs_function is None:
                            # Default job processing:
                            # Send I/O operation to the device
                            try:
                                func(*args)
                            except Exception as err:
                                pft(err)
                        else:
                            # User-supplied job processing
                            self.alt_process_jobs_function(func, args)

                    # Put sentinel back in
                    self.queue.put(self.sentinel)

                if self.DEBUG:
                    dprint("Worker_send %s: unlock # %i" % 
                           (self.dev.name, self.update_counter),
                           self.DEBUG_color)

                locker.unlock()
                locker_wait.unlock()

            if self.DEBUG:
                dprint("Worker_send %s: done running" % self.dev.name,
                       self.DEBUG_color)

        @QtCore.pyqtSlot()
        def _stop(self):
            """Stop the worker to prepare for quitting the worker thread
            """
            self.running = False
            self.qwc.wakeAll()

        # ----------------------------------------------------------------------
        #   add_to_queue
        # ----------------------------------------------------------------------

        def add_to_queue(self, instruction, pass_args=()):
            """Put an instruction on the worker_send queue.
            E.g. add_to_queue(self.dev.write, "toggle LED")

            Args:
                instruction:
                    Intended to be a reference to a device I/O function such as
                    'self.dev.write'. However, you have the freedom to be
                    creative and put e.g. strings decoding special instructions
                    on the queue as well. Handling such special cases must be
                    programmed by the user by supplying the argument
                    'alt_process_jobs_function', when instantiating
                    'Worker_send', with your own job-processing-routines
                    function. See 'Worker_send' for more details.

                pass_args (optional, default=()):
                    Argument(s) to be passed to the instruction. Must be a
                    tuple, but for convenience any other type will also be
                    accepted if it concerns just a single argument that needs to
                    be passed.
            """
            if type(pass_args) is not tuple: pass_args = (pass_args,)
            self.queue.put((instruction, *pass_args))

        # ----------------------------------------------------------------------
        #   process_queue
        # ----------------------------------------------------------------------

        def process_queue(self):
            """Trigger processing the worker_send queue.
            """
            self.qwc.wakeAll()

        # ----------------------------------------------------------------------
        #   queued_instruction
        # ----------------------------------------------------------------------

        def queued_instruction(self, instruction, pass_args=()):
            """Put an instruction on the worker_send queue and process the
            queue. See 'add_to_queue' for more details.
            """
            self.add_to_queue(instruction, pass_args)
            self.process_queue()
