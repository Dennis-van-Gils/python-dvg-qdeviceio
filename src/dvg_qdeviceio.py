#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt/PySide framework for multithreaded data acquisition and communication
with an I/O device.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-qdeviceio"
__date__ = "24-06-2024"
__version__ = "1.6.0"
# pylint: disable=protected-access, too-many-lines

import sys
import queue
import time
from enum import IntEnum, unique
from typing import Union, Callable

# Code coverage tools 'coverage' and 'pytest-cov' don't seem to correctly trace
# code which is inside methods called from within QThreads, see
# https://github.com/nedbat/coveragepy/issues/686
# To mitigate this problem, I use a custom decorator '@_coverage_resolve_trace'
# to be hung onto those method definitions. This will prepend the decorated
# method code with 'sys.settrace(threading._trace_hook)' when a code
# coverage test is detected. When no coverage test is detected, it will just
# pass the original method untouched.
import threading
from functools import wraps

import numpy as np

from qtpy import QtCore
from qtpy.QtCore import Signal, Slot  # type: ignore

from dvg_debug_functions import (
    print_fancy_traceback as pft,
    dprint,
    tprint,
    ANSI,
)

running_coverage = "coverage" in sys.modules
if running_coverage:
    print("\nCode coverage test detected\n")


def _coverage_resolve_trace(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if running_coverage:
            sys.settrace(threading._trace_hook)  # type: ignore
        fn(*args, **kwargs)

    return wrapped


# Short-hand alias for DEBUG information
def _cur_thread_name():
    return QtCore.QThread.currentThread().objectName()


@unique
class DAQ_TRIGGER(IntEnum):
    """An enumeration decoding different modes of operation for
    :class:`Worker_DAQ` to perform a data-acquisition (DAQ) update.
    """

    # fmt: off
    INTERNAL_TIMER = 0       #: :ref:`Link to background information <INTERNAL_TIMER>`.
    SINGLE_SHOT_WAKE_UP = 1  #: :ref:`Link to background information <SINGLE_SHOT_WAKE_UP>`.
    CONTINUOUS = 2           #: :ref:`Link to background information <CONTINUOUS>`.
    # fmt: on


class _NoDevice:
    name = "NoDevice"
    is_alive = False
    mutex = QtCore.QMutex()


# ------------------------------------------------------------------------------
#   QDeviceIO
# ------------------------------------------------------------------------------


class QDeviceIO(QtCore.QObject):
    """This class provides the framework for multithreaded data acquisition
    (DAQ) and communication with an I/O device.

    All device I/O operations will be offloaded to *workers*, each running in
    their dedicated thread. The following workers can be created:

    * :class:`Worker_DAQ` :

        Acquires data from the device, either periodically or aperiodically.

        Created by calling :meth:`create_worker_DAQ`.

    * :class:`Worker_jobs` :

        Maintains a thread-safe queue where desired device I/O operations,
        called *jobs*, can be put onto. It will send out the queued jobs
        first-in, first-out (FIFO) to the device.

        Created by calling :meth:`create_worker_jobs`.

    Tip:
        You can inherit from `QDeviceIO` to build your own subclass that
        hides the specifics of creating :class:`Worker_DAQ` and
        :class:`Worker_jobs` from the user and modifies the default parameter
        values. E.g., when making a `QDeviceIO` subclass specific to your
        Arduino project::

            from dvg_qdeviceio import QDeviceIO, DAQ_TRIGGER

            class Arduino_qdev(QDeviceIO):
                def __init__(
                    self, dev=None, DAQ_function=None, debug=False, **kwargs,
                ):
                    # Pass `dev` onto QDeviceIO() and pass `**kwargs` onto QtCore.QObject()
                    super().__init__(dev, **kwargs)

                    # Set the DAQ to 10 Hz internal timer
                    self.create_worker_DAQ(
                        DAQ_trigger                = DAQ_TRIGGER.INTERNAL_TIMER,
                        DAQ_function               = DAQ_function,
                        DAQ_interval_ms            = 100,  # 100 ms -> 10 Hz
                        critical_not_alive_count   = 3,
                        debug                      = debug,
                    )

                    # Standard jobs handling
                    self.create_worker_jobs(debug=debug)

        Now, the user only has to call the following to get up and running::

            ard_qdev = Arduino_qdev(
                dev=my_Arduino_device,
                DAQ_function=my_DAQ_function
            )
            ard_qdev.start()

    .. _`QDeviceIO_args`:

    Args:
        dev (:obj:`object` | :obj:`_NoDevice`, optional):
            Reference to a user-supplied *device* class instance containing
            I/O methods. In addition, `dev` should also have the following
            members. If not, they will be injected into the `dev` instance for
            you:

                * **dev.name** (:obj:`str`) -- Short display name for the \
                    device. Default: "myDevice".

                * **dev.mutex** (:class:`PySide6.QtCore.QMutex`) -- To allow \
                    for properly multithreaded device I/O operations. It will \
                    be used by :class:`Worker_DAQ` and :class:`Worker_jobs`.

                * **dev.is_alive** (:obj:`bool`) -- Device is up and \
                    communicatable? Default: :const:`True`.

            Default: :obj:`_NoDevice`

        **kwargs:
            All remaining keyword arguments will be passed onto inherited class
            :class:`PySide6.QtCore.QObject`.

    .. _`QDeviceIO_attributes`:
    .. rubric:: Attributes:

    Attributes:
        dev (:obj:`object` | :obj:`_NoDevice`):
            Reference to a user-supplied *device* class instance containing
            I/O methods.

        worker_DAQ (:class:`Worker_DAQ`):
            Instance of :class:`Worker_DAQ` as created by
            :meth:`create_worker_DAQ`. This worker runs in a dedicated thread.

        worker_jobs (:class:`Worker_jobs`):
            Instance of :class:`Worker_jobs` as created by
            :meth:`create_worker_jobs`. This worker runs in a dedicated thread.

        update_counter_DAQ (:obj:`int`):
            Increments every time :attr:`worker_DAQ` tries to update.

        update_counter_jobs (:obj:`int`):
            Increments every time :attr:`worker_jobs` tries to update.

        obtained_DAQ_interval_ms (:obj:`int` | :obj:`numpy.nan`):
            Obtained time interval in milliseconds since the previous
            :attr:`worker_DAQ` update.

        obtained_DAQ_rate_Hz (:obj:`float` | :obj:`numpy.nan`):
            Obtained acquisition rate of :attr:`worker_DAQ` in hertz. It will
            take several DAQ updates for the value to be properly calculated,
            and till that time it will be :obj:`numpy.nan`.

        not_alive_counter_DAQ (:obj:`int`):
            Number of consecutive failed attempts to update :attr:`worker_DAQ`,
            presumably due to device I/O errors. Will be reset to 0 once a
            successful DAQ update occurs. See the
            :obj:`signal_connection_lost()` mechanism.
    """

    signal_DAQ_updated = Signal()
    """:obj:`PySide6.QtCore.pyqtSignal`: Emitted by :class:`Worker_DAQ` when its
    :ref:`DAQ_function <arg_DAQ_function>` has run and finished, either
    succesfully or not.

    Tip:
        It can be useful to connect this signal to a slot containing, e.g.,
        your GUI redraw routine::

            from PySide6 import QtCore

            @QtCore.pyqtSlot()
            def my_GUI_redraw_routine():
                ...

            qdev.signal_DAQ_updated.connect(my_GUI_redraw_routine)

        where ``qdev`` is your instance of :class:`QDeviceIO`. Don't forget to
        decorate the function definition with a :func:`PySide6.QtCore.pyqtSlot`
        decorator.
    """

    signal_jobs_updated = Signal()
    """:obj:`PySide6.QtCore.pyqtSignal`: Emitted by :class:`Worker_jobs` when all
    pending jobs in the queue have been sent out to the device in a response to
    :meth:`send` or :meth:`process_jobs_queue`. See also the tip at
    :obj:`signal_DAQ_updated()`.
    """

    signal_DAQ_paused = Signal()
    """:obj:`PySide6.QtCore.pyqtSignal`: Emitted by :class:`Worker_DAQ` to confirm
    the worker has entered the `paused` state in a response to
    :meth:`pause_DAQ`. See also the tip at :obj:`signal_DAQ_updated()`.
    """

    signal_connection_lost = Signal()
    """:obj:`PySide6.QtCore.pyqtSignal`: Emitted by :class:`Worker_DAQ` to
    indicate that we have lost connection to the device. This happens when `N`
    consecutive device I/O operations have failed, where `N` equals the argument
    :obj:`critical_not_alive_count` as passed to method
    :meth:`create_worker_DAQ`. See also the tip at :obj:`signal_DAQ_updated()`.
    """

    # Necessary for INTERNAL_TIMER
    _request_worker_DAQ_stop = Signal()

    # Necessary for CONTINUOUS
    _request_worker_DAQ_pause = Signal()
    _request_worker_DAQ_unpause = Signal()

    def __init__(self, dev=_NoDevice(), **kwargs):
        super().__init__(**kwargs)  # Pass **kwargs onto QtCore.QObject()

        if not hasattr(dev, "name"):
            dev.name = "myDevice"

        if not hasattr(dev, "mutex"):
            dev.mutex = QtCore.QMutex()

        if not hasattr(dev, "is_alive"):
            dev.is_alive = True  # Assume the device is alive from the start

        self.dev = dev

        self._thread_DAQ = None
        self._thread_jobs = None

        self.worker_DAQ = Uninitialized_Worker_DAQ
        self.worker_jobs = Uninitialized_Worker_jobs

        self.update_counter_DAQ = 0
        self.update_counter_jobs = 0
        self.not_alive_counter_DAQ = 0

        self.obtained_DAQ_interval_ms = np.nan
        self.obtained_DAQ_rate_Hz = np.nan

        self._qwc_worker_DAQ_started = QtCore.QWaitCondition()
        self._qwc_worker_jobs_started = QtCore.QWaitCondition()

        self._qwc_worker_DAQ_stopped = QtCore.QWaitCondition()
        self._qwc_worker_jobs_stopped = QtCore.QWaitCondition()
        self._mutex_wait_worker_DAQ = QtCore.QMutex()
        self._mutex_wait_worker_jobs = QtCore.QMutex()

    # --------------------------------------------------------------------------
    #   Create workers
    # --------------------------------------------------------------------------

    def create_worker_DAQ(
        self,
        DAQ_trigger: DAQ_TRIGGER = DAQ_TRIGGER.INTERNAL_TIMER,
        DAQ_function: Union[Callable, None] = None,
        DAQ_interval_ms: int = 100,
        DAQ_timer_type: QtCore.Qt.TimerType = QtCore.Qt.TimerType.PreciseTimer,
        critical_not_alive_count: int = 1,
        debug: bool = False,
        **kwargs,
    ):
        """Create and configure an instance of :class:`Worker_DAQ` and transfer
        it to a new :class:`PySide6.QtCore.QThread`.

        This worker acquires data from the I/O device, either periodically or
        aperiodically. It does so by calling a user-supplied function, passed as
        parameter :ref:`DAQ_function <arg_DAQ_function>`, containing device I/O
        operations and subsequent data processing, every time the worker
        *updates*. There are different modes of operation for this worker to
        perform an *update*. This is set by parameter :obj:`DAQ_trigger`.

        The *Worker_DAQ* routine is robust in the following sense. It can be set
        to quit as soon as a communication error appears, or it could be set to
        allow a certain number of communication errors before it quits. The
        latter can be useful in non-critical implementations where continuity of
        the program is of more importance than preventing drops in data
        transmission. This, obviously, is a work-around for not having to tackle
        the source of the communication error, but sometimes you just need to
        struggle on. E.g., when your Arduino is out in the field and picks up
        occasional unwanted interference/ground noise that messes with your data
        transmission. See parameter :obj:`critical_not_alive_count`.

        Args:
            DAQ_trigger (:obj:`int`, optional):
                Mode of operation. See :class:`DAQ_TRIGGER`.

                Default: :const:`DAQ_TRIGGER.INTERNAL_TIMER`.

                .. _`arg_DAQ_function`:

            DAQ_function (:obj:`Callable` | :obj:`None`, optional):
                Reference to a user-supplied function containing the device
                I/O operations and subsequent data processing, to be invoked
                every DAQ update.

                Default: :obj:`None`.

                Important:
                    The function must return :const:`True` when the communication
                    with the device was successful, and :const:`False` otherwise.

                Warning:
                    **Neither directly change the GUI, nor print to the terminal
                    from out of this function.** Doing so might temporarily suspend
                    the function and could mess with the timing stability of the
                    worker. (You're basically undermining the reason to have
                    multithreading in the first place). That could be acceptable,
                    though, when you need to print debug or critical error
                    information to the terminal, but be aware about the possible
                    negative effects.

                    Instead, connect to :meth:`QDeviceIO.signal_DAQ_updated` from
                    out of the *main/GUI* thread to instigate changes to the
                    terminal/GUI when needed.

                Example:
                    Pseudo-code, where ``time`` and ``temperature`` are variables
                    that live at a higher scope, presumably at the *main* scope
                    level. The function ``dev.query_temperature()`` contains the
                    device I/O operations, e.g., sending out a query over RS232 and
                    collecting the device reply. In addition, the function notifies
                    if the communication was successful. Hence, the return values of
                    ``dev.query_temperature()`` are ``success`` as boolean and
                    ``reply`` as a tuple containing a time stamp and a temperature
                    reading. ::

                        def my_DAQ_function():
                            success, reply = dev.query_temperature()
                            if not(success):
                                print("Device IOerror")
                                return False    # Return failure

                            # Parse readings into separate variables and store them
                            try:
                                time, temperature = reply
                            except Exception as err:
                                print(err)
                                return False    # Return failure

                            return True         # Return success

            DAQ_interval_ms (:obj:`int`, optional):
                Only useful in mode :const:`DAQ_TRIGGER.INTERNAL_TIMER`. Desired
                data-acquisition update interval in milliseconds.

                Default: :const:`100`.

            DAQ_timer_type (:class:`PySide6.QtCore.Qt.TimerType`, optional):
                Only useful in mode :const:`DAQ_TRIGGER.INTERNAL_TIMER`.
                The update interval is timed to a :class:`PySide6.QtCore.QTimer`
                running inside :class:`Worker_DAQ`. The default value
                :const:`PySide6.QtCore.Qt.TimerType.PreciseTimer` tries to ensure the
                best possible timer accuracy, usually ~1 ms granularity depending on
                the OS, but it is resource heavy so use sparingly. One can reduce
                the CPU load by setting it to less precise timer types
                :const:`PySide6.QtCore.Qt.TimerType.CoarseTimer` or
                :const:`PySide6.QtCore.Qt.TimerType.VeryCoarseTimer`.

                Default: :const:`PySide6.QtCore.Qt.TimerType.PreciseTimer`.

                .. _`arg_critical_not_alive_count`:

            critical_not_alive_count (:obj:`int`, optional):
                The worker will allow for up to a certain number of consecutive
                communication failures with the device, before hope is given up
                and a :meth:`QDeviceIO.signal_connection_lost` is emitted. Use at
                your own discretion. Setting the value to 0 will never give up
                on communication failures.

                Default: :const:`1`.

            debug (:obj:`bool`, optional):
                Print debug info to the terminal? Warning: Slow! Do not leave on
                unintentionally.

                Default: :const:`False`.

            **kwargs:
                All remaining keyword arguments will be passed onto inherited class
                :class:`PySide6.QtCore.QObject`.
        """
        if isinstance(self.dev, _NoDevice):
            pft("Can't create worker_DAQ, because there is no device attached.")
            sys.exit(99)

        self.worker_DAQ = Worker_DAQ(
            qdev=self,
            DAQ_trigger=DAQ_trigger,
            DAQ_function=DAQ_function,
            DAQ_interval_ms=DAQ_interval_ms,
            DAQ_timer_type=DAQ_timer_type,
            critical_not_alive_count=critical_not_alive_count,
            debug=debug,
            **kwargs,
        )

        self._request_worker_DAQ_stop.connect(self.worker_DAQ._stop)
        self._request_worker_DAQ_pause.connect(self.worker_DAQ._set_pause_true)
        self._request_worker_DAQ_unpause.connect(
            self.worker_DAQ._set_pause_false
        )

        self._thread_DAQ = QtCore.QThread()
        self._thread_DAQ.setObjectName(f"{self.dev.name}_DAQ")
        self._thread_DAQ.started.connect(self.worker_DAQ._do_work)
        self.worker_DAQ.moveToThread(self._thread_DAQ)

        if hasattr(self.worker_DAQ, "_timer"):
            self.worker_DAQ._timer.moveToThread(self._thread_DAQ)

    def create_worker_jobs(
        self,
        jobs_function: Union[Callable, None] = None,
        debug: bool = False,
        **kwargs,
    ):
        """Create and configure an instance of :class:`Worker_jobs` and transfer
        it to a new :class:`PySide6.QtCore.QThread`.

        This worker maintains a thread-safe queue where desired device I/O
        operations, called *jobs*, can be put onto. The worker will send out the
        operations to the device, first-in, first-out (FIFO), until the queue is
        empty again. The manner in which each job gets handled is explained by
        parameter :obj:`jobs_function`.

        This worker uses the :class:`PySide6.QtCore.QWaitCondition` mechanism.
        Hence, it will only send out all pending jobs on the queue, whenever the
        thread is woken up by a call to :meth:`Worker_jobs.process_queue()`.
        When it has emptied the queue, the thread will go back to sleep again.

        Args:
            jobs_function (:obj:`Callable` | :obj:`None`, optional):
                Routine to be performed per job.

                Default: :obj:`None`.

                When omitted and, hence, left set to the default value
                :obj:`None`, it will perform the default job handling routine,
                which goes as follows:

                    ``func`` and ``args`` will be retrieved from the jobs
                    queue and their combination ``func(*args)`` will get
                    executed. Respectively, *func* and *args* correspond to
                    *instruction* and *pass_args* of methods :meth:`send` and
                    :meth:`add_to_queue`.

                The default is sufficient when ``func`` corresponds to an I/O
                operation that is an one-way send, i.e. a write operation with
                optionally passed arguments, but without a reply from the
                device.

                Alternatively, you can pass it a reference to a user-supplied
                function performing an alternative job handling routine. This
                allows you to get creative and put, e.g., special string
                messages on the queue that decode into, e.g.,

                - multiple write operations to be executed as one block,
                - query operations whose return values can be acted upon
                  accordingly,
                - extra data processing in between I/O operations.

                The function you supply must take two arguments, where the first
                argument is to be ``func`` and the second argument is to be
                ``args`` of type :obj:`tuple`. Both ``func`` and ``args`` will
                be retrieved from the jobs queue and passed onto your supplied
                function.

                Warning:
                    **Neither directly change the GUI, nor print to the terminal
                    from out of this function.** Doing so might temporarily
                    suspend the function and could mess with the timing
                    stability of the worker. (You're basically undermining the
                    reason to have multithreading in the first place). That
                    could be acceptable, though, when you need to print debug or
                    critical error information to the terminal, but be aware
                    about this warning.

                    Instead, connect to :meth:`QDeviceIO.signal_jobs_updated`
                    from out of the *main/GUI* thread to instigate changes to
                    the terminal/GUI when needed.

                Example::

                    def my_jobs_function(func, args):
                        if func == "query_id?":
                            # Query the device for its identity string
                            success, ans_str = dev.query("id?")
                            # And store the reply 'ans_str' in another variable
                            # at a higher scope or do stuff with it here.
                        else:
                            # Default job handling where, e.g.
                            # func = dev.write
                            # args = ("toggle LED",)
                            func(*args)

            debug (:obj:`bool`, optional):
                Print debug info to the terminal? Warning: Slow! Do not leave on
                unintentionally.

                Default: :const:`False`.

            **kwargs:
                All remaining keyword arguments will be passed onto inherited
                class :class:`PySide6.QtCore.QObject`.
        """
        if isinstance(self.dev, _NoDevice):
            pft(
                "Can't create worker_jobs, because there is no device attached."
            )
            sys.exit(99)

        self.worker_jobs = Worker_jobs(
            qdev=self,
            jobs_function=jobs_function,
            debug=debug,
            **kwargs,
        )

        self._thread_jobs = QtCore.QThread()
        self._thread_jobs.setObjectName(f"{self.dev.name}_jobs")
        self._thread_jobs.started.connect(self.worker_jobs._do_work)
        self.worker_jobs.moveToThread(self._thread_jobs)

    # --------------------------------------------------------------------------
    #   Start workers
    # --------------------------------------------------------------------------

    def start(
        self,
        DAQ_priority=QtCore.QThread.Priority.InheritPriority,
        jobs_priority=QtCore.QThread.Priority.InheritPriority,
    ) -> bool:
        """Start the event loop of all of any created workers.

        Args:
            DAQ_priority (:class:`PySide6.QtCore.QThread.Priority`, optional):
                By default, the *worker* threads run in the operating system
                at the same thread priority as the *main/GUI* thread. You can
                change to higher priority by setting `priority` to, e.g.,
                :const:`PySide6.QtCore.QThread.TimeCriticalPriority`. Be aware
                that this is resource heavy, so use sparingly.

                Default: :const:`PySide6.QtCore.QThread.Priority.InheritPriority`.

            jobs_priority (:class:`PySide6.QtCore.QThread.Priority`, optional):
                Like `DAQ_priority`.

                Default: :const:`PySide6.QtCore.QThread.Priority.InheritPriority`.

        Returns:
            True if successful, False otherwise.
        """
        success = True

        if self._thread_jobs is not None:
            success &= self.start_worker_jobs(priority=jobs_priority)

        if self._thread_DAQ is not None:
            success &= self.start_worker_DAQ(priority=DAQ_priority)

        return success

    def start_worker_DAQ(
        self, priority=QtCore.QThread.Priority.InheritPriority
    ) -> bool:
        """Start the data acquisition with the device by starting the event loop
        of the :attr:`worker_DAQ` thread.

        Args:
            priority (:class:`PySide6.QtCore.QThread.Priority`, optional):
                See :meth:`start` for details.

        Returns:
            True if successful, False otherwise.
        """
        if (
            self._thread_DAQ is None
            or self.worker_DAQ is Uninitialized_Worker_DAQ
        ):
            pft(
                f"Worker_DAQ  {self.dev.name}: Can't start thread, because it "
                "does not exist. Did you forget to call 'create_worker_DAQ()' "
                "first?"
            )
            sys.exit(404)  # --> leaving

        elif not self.dev.is_alive:
            dprint(
                f"Worker_DAQ  {self.dev.name}: "
                "WARNING - Device is not alive.\n",
                ANSI.RED,
            )
            return False  # --> leaving

        if self.worker_DAQ.debug:
            tprint(
                f"Worker_DAQ  {self.dev.name}: start requested...",
                ANSI.WHITE,
            )

        self._thread_DAQ.start(priority)

        # Wait for worker_DAQ to confirm having started
        locker_wait = QtCore.QMutexLocker(self._mutex_wait_worker_DAQ)
        self._qwc_worker_DAQ_started.wait(self._mutex_wait_worker_DAQ)
        locker_wait.unlock()

        if self.worker_DAQ._DAQ_trigger == DAQ_TRIGGER.SINGLE_SHOT_WAKE_UP:
            # Wait a tiny amount of extra time for the worker to have entered
            # 'self._qwc.wait(self._mutex_wait)' of method '_do_work()'.
            # Unfortunately, we can't use
            #   'QTimer.singleShot(500, confirm_has_started(self))'
            # inside the '_do_work()' routine, because it won't never resolve
            # due to the upcoming blocking 'self._qwc.wait(self._mutex_wait)'.
            # Hence, we use a blocking 'time.sleep()' here. Also note we can't
            # use 'QtCore.QCoreApplication.processEvents()' instead of
            # 'time.sleep()', because it involves a QWaitCondition and not an
            # signal event.
            time.sleep(0.05)

        if self.worker_DAQ._DAQ_trigger == DAQ_TRIGGER.CONTINUOUS:
            # We expect a 'signal_DAQ_paused' being emitted at start-up by this
            # worker. Make sure this signal gets processed as soon as possible,
            # and prior to any other subsequent actions the user might request
            # from this worker after having returned back from the user's call
            # to 'start_worker_DAQ()'.
            QtCore.QCoreApplication.processEvents()

        return True

    def start_worker_jobs(
        self, priority=QtCore.QThread.Priority.InheritPriority
    ) -> bool:
        """Start maintaining the jobs queue by starting the event loop of the
        :attr:`worker_jobs` thread.

        Args:
            priority (:class:`PySide6.QtCore.QThread.Priority`, optional):
                See :meth:`start` for details.

        Returns:
            True if successful, False otherwise.
        """
        if (
            self._thread_jobs is None
            or self.worker_jobs is Uninitialized_Worker_jobs
        ):
            pft(
                f"Worker_jobs {self.dev.name}: Can't start thread because it "
                "does not exist. Did you forget to call 'create_worker_jobs()' "
                "first?"
            )
            sys.exit(404)  # --> leaving

        elif not self.dev.is_alive:
            dprint(
                f"Worker_jobs {self.dev.name}: "
                "WARNING - Device is not alive.\n",
                ANSI.RED,
            )
            return False  # --> leaving

        if self.worker_jobs.debug:
            tprint(
                f"Worker_jobs {self.dev.name}: start requested...",
                ANSI.WHITE,
            )

        self._thread_jobs.start(priority)

        # Wait for worker_jobs to confirm having started
        locker_wait = QtCore.QMutexLocker(self._mutex_wait_worker_jobs)
        self._qwc_worker_jobs_started.wait(self._mutex_wait_worker_jobs)
        locker_wait.unlock()

        # Wait a tiny amount of extra time for the worker to have entered
        # 'self._qwc.wait(self._mutex_wait)' of method '_do_work()'.
        # Unfortunately, we can't use
        #   'QTimer.singleShot(500, confirm_has_started(self))'
        # inside the '_do_work()' routine, because it won't never resolve
        # due to the upcoming blocking 'self._qwc.wait(self._mutex_wait)'.
        # Hence, we use a blocking 'time.sleep()' here. Also note we can't
        # use 'QtCore.QCoreApplication.processEvents()' instead of
        # 'time.sleep()', because it involves a QWaitCondition and not an
        # signal event.
        time.sleep(0.05)

        return True

    # --------------------------------------------------------------------------
    #   Quit workers
    # --------------------------------------------------------------------------

    def quit(self) -> bool:
        """Stop all of any running workers and close their respective threads.

        Returns:
            True if successful, False otherwise.
        """
        return self.quit_worker_DAQ() & self.quit_worker_jobs()

    def quit_worker_DAQ(self) -> bool:
        """Stop :attr:`worker_DAQ` and close its thread.

        Returns:
            True if successful, False otherwise.
        """

        if (
            self._thread_DAQ is None
            or self.worker_DAQ is Uninitialized_Worker_DAQ
            or not self.worker_DAQ._has_started
        ):
            return True

        if self._thread_DAQ.isFinished():
            # CASE: Device has had a 'connection_lost' event during run-time,
            # which already stopped and closed the thread.
            print(
                "Closing thread "
                f"{self._thread_DAQ.objectName():.<16} already closed."
            )
            return True

        if not self.worker_DAQ._has_stopped:
            if self.worker_DAQ.debug:
                tprint(
                    f"Worker_DAQ  {self.dev.name}: stop requested...",
                    ANSI.WHITE,
                )

            if self.worker_DAQ._DAQ_trigger == DAQ_TRIGGER.INTERNAL_TIMER:
                # The QTimer inside the INTERNAL_TIMER '_do_work()'-routine
                # /must/ be stopped from within the worker_DAQ thread. Hence,
                # we must use a signal from out of this different thread.
                self._request_worker_DAQ_stop.emit()

            elif (
                self.worker_DAQ._DAQ_trigger == DAQ_TRIGGER.SINGLE_SHOT_WAKE_UP
            ):
                # The QWaitCondition inside the SINGLE_SHOT_WAKE_UP '_do_work()'
                # routine will likely have locked worker_DAQ. Hence, a
                # '_request_worker_DAQ_stop' signal as above might not get
                # handled by worker_DAQ when emitted from out of this thread.
                # Instead, we directly call '_stop()' from out of this different
                # thread, which is perfectly fine for SINGLE_SHOT_WAKE_UP as per
                # my design.
                self.worker_DAQ._stop()

            elif self.worker_DAQ._DAQ_trigger == DAQ_TRIGGER.CONTINUOUS:
                # We directly call '_stop()' from out of this different thread,
                # which is perfectly fine for CONTINUOUS as per my design.
                self.worker_DAQ._stop()

            # Wait for worker_DAQ to confirm having stopped
            locker_wait = QtCore.QMutexLocker(self._mutex_wait_worker_DAQ)
            self._qwc_worker_DAQ_stopped.wait(self._mutex_wait_worker_DAQ)
            locker_wait.unlock()

        self._thread_DAQ.quit()
        print(f"Closing thread {self._thread_DAQ.objectName():.<16} ", end="")
        if self._thread_DAQ.wait(2000):
            print("done.\n", end="")
            return True

        print("FAILED.\n", end="")  # pragma: no cover
        return False  # pragma: no cover

    def quit_worker_jobs(self) -> bool:
        """Stop :attr:`worker_jobs` and close its thread.

        Returns:
            True if successful, False otherwise.
        """

        if (
            self._thread_jobs is None
            or self.worker_jobs is Uninitialized_Worker_jobs
            or not self.worker_jobs._has_started
        ):
            return True

        if self._thread_jobs.isFinished():
            # CASE: Device has had a 'connection_lost' event during run-time,
            # which already stopped the worker and closed the thread.
            print(
                "Closing thread "
                f"{self._thread_jobs.objectName():.<16} already closed."
            )
            return True

        if not self.worker_jobs._has_stopped:
            if self.worker_jobs.debug:
                tprint(
                    f"Worker_jobs {self.dev.name}: stop requested...",
                    ANSI.WHITE,
                )

            # The QWaitCondition inside the SINGLE_SHOT_WAKE_UP '_do_work()'-
            # routine will likely have locked worker_DAQ. Hence, a
            # '_request_worker_DAQ_stop' signal might not get handled by
            # worker_DAQ when emitted from out of this thread. Instead,
            # we directly call '_stop()' from out of this different thread,
            # which is perfectly fine as per my design.
            self.worker_jobs._stop()

            # Wait for worker_jobs to confirm having stopped
            locker_wait = QtCore.QMutexLocker(self._mutex_wait_worker_jobs)
            self._qwc_worker_jobs_stopped.wait(self._mutex_wait_worker_jobs)
            locker_wait.unlock()

        self._thread_jobs.quit()
        print(f"Closing thread {self._thread_jobs.objectName():.<16} ", end="")
        if self._thread_jobs.wait(2000):
            print("done.\n", end="")
            return True

        print("FAILED.\n", end="")  # pragma: no cover
        return False  # pragma: no cover

    # --------------------------------------------------------------------------
    #   worker_DAQ related
    # --------------------------------------------------------------------------

    # @Slot()  # Commented out: Decorator not needed, it hides linter docstring
    def pause_DAQ(self):
        """Only useful in mode :const:`DAQ_TRIGGER.CONTINUOUS`. Request
        :attr:`worker_DAQ` to pause and stop listening for data. After
        :attr:`worker_DAQ` has achieved the `paused` state, it will emit
        :obj:`signal_DAQ_paused()`.
        """
        if self.worker_DAQ is not Uninitialized_Worker_DAQ:
            self._request_worker_DAQ_pause.emit()

    # @Slot()  # Commented out: Decorator not needed, it hides linter docstring
    def unpause_DAQ(self):
        """Only useful in mode :const:`DAQ_TRIGGER.CONTINUOUS`. Request
        :attr:`worker_DAQ` to resume listening for data. Once
        :attr:`worker_DAQ` has successfully resumed, it will emit
        :obj:`signal_DAQ_updated()` for every DAQ update.
        """
        if self.worker_DAQ is not Uninitialized_Worker_DAQ:
            self._request_worker_DAQ_unpause.emit()

    # @Slot()  # Commented out: Decorator not needed, it hides linter docstring
    def wake_up_DAQ(self):
        """Only useful in mode :const:`DAQ_TRIGGER.SINGLE_SHOT_WAKE_UP`.
        Request :attr:`worker_DAQ` to wake up and perform a single update,
        i.e. run its :ref:`DAQ_function <arg_DAQ_function>` once. It will emit
        :obj:`signal_DAQ_updated()` after the DAQ_function has
        run, either successful or not.
        """
        if self.worker_DAQ is not Uninitialized_Worker_DAQ:
            self.worker_DAQ._wake_up()

    # --------------------------------------------------------------------------
    #   worker_jobs related
    # --------------------------------------------------------------------------

    # @Slot()  # Commented out: Decorator not needed, it hides linter docstring
    def send(self, instruction, pass_args=()):
        """Put a job on the :attr:`worker_jobs` queue and send out the full
        queue first-in, first-out to the device until empty. Once finished, it
        will emit :obj:`signal_jobs_updated()`.

        Args:
            instruction (:obj:`Callable` | *other*):
                Intended to be a reference to a device I/O method such as
                ``dev.write()``. Any arguments to be passed to the I/O method
                need to be set in the :attr:`pass_args` parameter.

                You have the freedom to be creative and put, e.g., strings
                decoding special instructions on the queue as well. Handling
                such special cases must be programmed by supplying the parameter
                :obj:`jobs_function` when calling
                :meth:`QDeviceIO.create_worker_jobs` with your own alternative
                job-processing-routine function.

            pass_args (:obj:`tuple` | *other*, optional):
                Arguments to be passed to the instruction. Must be given as a
                :obj:`tuple`, but for convenience any other type will also be
                accepted if it just concerns a single argument.

                Default: :obj:`()`.

        Example::

            qdev.send(dev.write, "toggle LED")

        where ``qdev`` is your :class:`QDeviceIO` class instance and ``dev`` is
        your *device* class instance containing I/O methods.
        """
        if self.worker_jobs is not Uninitialized_Worker_jobs:
            self.worker_jobs._send(instruction, pass_args)

    # @Slot()  # Commented out: Decorator not needed, it hides linter docstring
    def add_to_jobs_queue(self, instruction, pass_args=()):
        """Put a job on the :attr:`worker_jobs` queue.

        See :meth:`send` for details on the parameters.
        """
        if self.worker_jobs is not Uninitialized_Worker_jobs:
            self.worker_jobs._add_to_queue(instruction, pass_args)

    # @Slot()  # Commented out: Decorator not needed, it hides linter docstring
    def process_jobs_queue(self):
        """Send out the full :attr:`worker_jobs` queue first-in, first-out to
        the device until empty. Once finished, it will emit
        :obj:`signal_jobs_updated()`.
        """
        if self.worker_jobs is not Uninitialized_Worker_jobs:
            self.worker_jobs._process_queue()


# ------------------------------------------------------------------------------
#   Worker_DAQ
# ------------------------------------------------------------------------------


class Worker_DAQ(QtCore.QObject):
    """An instance of this worker will be created and placed inside a new thread
    when :meth:`QDeviceIO.create_worker_DAQ` gets called. See there for extended
    information.

    Args:
        qdev (:class:`QDeviceIO`):
            Reference to the parent :class:`QDeviceIO` class instance,
            automatically set when being initialized by
            :meth:`QDeviceIO.create_worker_DAQ`.

        DAQ_trigger (:obj:`int`, optional):

            Default: :const:`DAQ_TRIGGER.INTERNAL_TIMER`.

        DAQ_function (:obj:`Callable` | :obj:`None`, optional):

            Default: :obj:`None`.

        DAQ_interval_ms (:obj:`int`, optional):

            Default: :const:`100`.

        DAQ_timer_type (:class:`PySide6.QtCore.Qt.TimerType`, optional):

            Default: :const:`PySide6.QtCore.Qt.TimerType.PreciseTimer`.

        critical_not_alive_count (:obj:`int`, optional):

            Default: :const:`1`.

        debug (:obj:`bool`, optional):

            Default: :const:`False`.

        **kwargs:
            All remaining keyword arguments will be passed onto inherited class
            :class:`PySide6.QtCore.QObject`.

    .. rubric:: Attributes:

    Attributes:
        qdev (:class:`QDeviceIO`):
            Reference to the parent :class:`QDeviceIO` class instance.

        dev (:obj:`object` | :obj:`None`):
            Reference to the user-supplied *device* class instance containing
            I/O methods, automatically set when calling
            :meth:`QDeviceIO.create_worker_DAQ`. It is a shorthand for
            :obj:`self.qdev.dev`.

        DAQ_function (:obj:`Callable` | :obj:`None`):
            See :ref:`DAQ_function <arg_DAQ_function>`.

        critical_not_alive_count (:obj:`int`):
            See :ref:`critical_not_alive_count <arg_critical_not_alive_count>`.
    """

    def __init__(
        self,
        qdev: QDeviceIO,
        DAQ_trigger=DAQ_TRIGGER.INTERNAL_TIMER,
        DAQ_function=None,
        DAQ_interval_ms=100,
        DAQ_timer_type=QtCore.Qt.TimerType.PreciseTimer,
        critical_not_alive_count=1,
        debug=False,
        **kwargs,
    ):
        super().__init__(**kwargs)  # Pass **kwargs onto QtCore.QObject()
        self.debug = debug
        self.debug_color = ANSI.CYAN

        self.qdev = qdev
        self.dev = _NoDevice() if qdev is None else qdev.dev

        self._DAQ_trigger = DAQ_trigger
        self.DAQ_function = DAQ_function
        self._DAQ_interval_ms = DAQ_interval_ms
        self._DAQ_timer_type = DAQ_timer_type
        self.critical_not_alive_count = critical_not_alive_count

        self._has_started = False
        self._has_stopped = False

        # Keep track of the obtained DAQ interval and DAQ rate using
        # QElapsedTimer (QET)
        self._QET_interval = QtCore.QElapsedTimer()
        self._QET_rate = QtCore.QElapsedTimer()
        # Accumulates the number of DAQ updates passed since the previous DAQ
        # rate evaluation
        self._rate_accumulator = 0

        # Members specifically for INTERNAL_TIMER
        if self._DAQ_trigger == DAQ_TRIGGER.INTERNAL_TIMER:
            self._timer = QtCore.QTimer()
            self._timer.setInterval(DAQ_interval_ms)
            self._timer.setTimerType(DAQ_timer_type)
            self._timer.timeout.connect(self._perform_DAQ)

        # Members specifically for SINGLE_SHOT_WAKE_UP
        elif self._DAQ_trigger == DAQ_TRIGGER.SINGLE_SHOT_WAKE_UP:
            self._running = True
            self._qwc = QtCore.QWaitCondition()
            self._mutex_wait = QtCore.QMutex()

        # Members specifically for CONTINUOUS
        # Note: At start-up, the worker will directly go into a paused state
        # and trigger a 'signal_DAQ_paused' PyQt signal
        elif self._DAQ_trigger == DAQ_TRIGGER.CONTINUOUS:
            self._running = True

            self._pause = None
            """Will be set at init of '_do_work()' when 'start_worker_DAQ()' is
            called"""

            self._paused = None
            """Will be set at init of '_do_work()' when 'start_worker_DAQ()' is
            called"""

        if self.debug:
            tprint(
                f"Worker_DAQ  {self.dev.name}: "
                f"init @ thread {_cur_thread_name()}",
                self.debug_color,
            )

    # --------------------------------------------------------------------------
    #   _do_work
    # --------------------------------------------------------------------------

    @_coverage_resolve_trace
    @Slot()
    def _do_work(self):
        # fmt: off
        # Uncomment block to enable Visual Studio Code debugger to have access
        # to this thread. DO NOT LEAVE BLOCK UNCOMMENTED: Running it outside of
        # the debugger causes crashes.
        """
        if self.debug:
            import pydevd
            pydevd.settrace(suspend=False)
        """
        # fmt: on

        init = True

        def confirm_has_started(self):
            # Wait a tiny amount of extra time for QDeviceIO to have entered
            # 'self._qwc_worker_###_started.wait(self._mutex_wait_worker_###)'
            # of method 'start_worker_###()'.
            time.sleep(0.05)

            if self.debug:
                tprint(
                    f"Worker_DAQ  {self.dev.name}: has started",
                    self.debug_color,
                )

            # Send confirmation
            self.qdev._qwc_worker_DAQ_started.wakeAll()
            self._has_started = True

        if self.debug:
            tprint(
                f"Worker_DAQ  {self.dev.name}: "
                f"starting @ thread {_cur_thread_name()}",
                self.debug_color,
            )

        # INTERNAL_TIMER
        if self._DAQ_trigger == DAQ_TRIGGER.INTERNAL_TIMER:
            self._timer.start()
            confirm_has_started(self)

        # SINGLE_SHOT_WAKE_UP
        elif self._DAQ_trigger == DAQ_TRIGGER.SINGLE_SHOT_WAKE_UP:
            locker_wait = QtCore.QMutexLocker(self._mutex_wait)
            locker_wait.unlock()

            while self._running:
                locker_wait.relock()

                if self.debug:
                    tprint(
                        f"Worker_DAQ  {self.dev.name}: "
                        "waiting for wake-up trigger",
                        self.debug_color,
                    )

                if init:
                    confirm_has_started(self)
                    init = False

                self._qwc.wait(self._mutex_wait)

                if self.debug:
                    tprint(
                        f"Worker_DAQ  {self.dev.name}: has woken up",
                        self.debug_color,
                    )

                # Needed check to prevent _perform_DAQ() at final wake up
                # when _stop() has been called
                if self._running:
                    self._perform_DAQ()

                locker_wait.unlock()

            if self.debug:
                tprint(
                    f"Worker_DAQ  {self.dev.name}: has stopped",
                    self.debug_color,
                )

            # Wait a tiny amount for the other thread to have entered the
            # QWaitCondition lock, before giving a wakingAll().
            QtCore.QTimer.singleShot(
                100,
                self.qdev._qwc_worker_DAQ_stopped.wakeAll,
            )
            self._has_stopped = True

        # CONTINUOUS
        elif self._DAQ_trigger == DAQ_TRIGGER.CONTINUOUS:
            while self._running:
                QtCore.QCoreApplication.processEvents()  # Essential to fire and process signals

                if init:
                    self._pause = True
                    self._paused = True

                    if self.debug:
                        tprint(
                            f"Worker_DAQ  {self.dev.name}: starting up paused",
                            self.debug_color,
                        )

                    self.qdev.signal_DAQ_paused.emit()

                    confirm_has_started(self)
                    init = False

                if self._pause:  # == True
                    if self._pause != self._paused:
                        if self.debug and not init:
                            tprint(
                                f"Worker_DAQ  {self.dev.name}: has paused",
                                self.debug_color,
                            )
                        self.qdev.signal_DAQ_paused.emit()
                        self._paused = True

                    time.sleep(0.01)  # Do not hog the CPU while paused

                else:  # == False
                    if self._pause != self._paused:
                        if self.debug:
                            tprint(
                                f"Worker_DAQ  {self.dev.name}: has unpaused",
                                self.debug_color,
                            )
                        self._paused = False

                    self._perform_DAQ()

            if self.debug:
                tprint(
                    f"Worker_DAQ  {self.dev.name}: has stopped",
                    self.debug_color,
                )

            # Wait a tiny amount for 'create_worker_DAQ()', which is running
            # in a different thread than this one, to have entered the
            # QWaitCondition lock, before giving a wakingAll().
            QtCore.QTimer.singleShot(
                100,
                self.qdev._qwc_worker_DAQ_stopped.wakeAll,
            )
            self._has_stopped = True

    # --------------------------------------------------------------------------
    #   _perform_DAQ
    # --------------------------------------------------------------------------

    @_coverage_resolve_trace
    @Slot()
    def _perform_DAQ(self):
        locker = QtCore.QMutexLocker(self.dev.mutex)
        self.qdev.update_counter_DAQ += 1

        if self.debug:
            tprint(
                f"Worker_DAQ  {self.dev.name}: "
                f"lock   # {self.qdev.update_counter_DAQ}",
                self.debug_color,
            )

        # Keep track of the obtained DAQ interval and DAQ rate
        if not self._QET_interval.isValid():
            self._QET_interval.start()
            self._QET_rate.start()
        else:
            # Obtained DAQ interval
            self.qdev.obtained_DAQ_interval_ms = self._QET_interval.restart()

            # Obtained DAQ rate
            self._rate_accumulator += 1
            dT = self._QET_rate.elapsed()

            if dT >= 1000:  # Evaluate every N elapsed milliseconds. Hard-coded.
                self._QET_rate.restart()
                try:
                    self.qdev.obtained_DAQ_rate_Hz = (
                        self._rate_accumulator / dT * 1e3
                    )
                except ZeroDivisionError:  # pragma: no cover
                    self.qdev.obtained_DAQ_rate_Hz = np.nan  # pragma: no cover

                self._rate_accumulator = 0

        # ----------------------------------
        #   User-supplied DAQ function
        # ----------------------------------

        if self.DAQ_function is not None:
            try:
                success = self.DAQ_function()
            except Exception as err:  # pylint: disable=broad-except
                pft(err)
                dprint(
                    f"@ Worker_DAQ {self.dev.name}\n",
                    ANSI.RED,
                )
            else:
                if success:
                    # Did return True, hence was successfull
                    # --> Reset the 'not alive' counter
                    self.qdev.not_alive_counter_DAQ = 0
                else:
                    # Did return False, hence was unsuccessfull
                    self.qdev.not_alive_counter_DAQ += 1

        # ----------------------------------
        #   End user-supplied DAQ function
        # ----------------------------------

        if self.debug:
            tprint(
                f"Worker_DAQ  {self.dev.name}: "
                f"unlock # {self.qdev.update_counter_DAQ}",
                self.debug_color,
            )

        locker.unlock()

        # Check the not alive counter
        if (
            self.critical_not_alive_count > 0
            and self.qdev.not_alive_counter_DAQ >= self.critical_not_alive_count
        ):
            dprint(
                f"Worker_DAQ  {self.dev.name}: " f"Lost connection to device.",
                ANSI.RED,
            )
            self.dev.is_alive = False
            self._stop()
            self.qdev.signal_connection_lost.emit()
            return

        self.qdev.signal_DAQ_updated.emit()

    # --------------------------------------------------------------------------
    #   _stop
    # --------------------------------------------------------------------------

    @Slot()
    def _stop(self):
        """Stop the worker to prepare for quitting the worker thread.

        This method should not be called from another thread when using
        `DAQ_TRIGGER.INTERNAL_TIMER`.
        """
        if self.debug:
            tprint(f"Worker_DAQ  {self.dev.name}: stopping", self.debug_color)

        if self._DAQ_trigger == DAQ_TRIGGER.INTERNAL_TIMER:
            # NOTE: The timer /must/ be stopped from the worker_DAQ thread!
            self._timer.stop()

            if self.debug:
                tprint(
                    f"Worker_DAQ  {self.dev.name}: has stopped",
                    self.debug_color,
                )

            # Wait a tiny amount for the other thread to have entered the
            # QWaitCondition lock, before giving a wakingAll().
            QtCore.QTimer.singleShot(
                100,
                self.qdev._qwc_worker_DAQ_stopped.wakeAll,
            )
            self._has_stopped = True

        elif self._DAQ_trigger == DAQ_TRIGGER.SINGLE_SHOT_WAKE_UP:
            self._running = False
            self._qwc.wakeAll()  # Wake up for the final time

        elif self._DAQ_trigger == DAQ_TRIGGER.CONTINUOUS:
            self._running = False

    # --------------------------------------------------------------------------
    #   _set_pause_true / _set_pause_false
    # --------------------------------------------------------------------------

    @Slot()
    def _set_pause_true(self):
        """Only useful in mode :const:`DAQ_TRIGGER.CONTINUOUS`. Pause
        the worker to stop listening for data. After :attr:`worker_DAQ` has
        achieved the `paused` state, it will emit :obj:`signal_DAQ_paused()`.

        This method should not be called from another thread.
        """
        if self._DAQ_trigger == DAQ_TRIGGER.CONTINUOUS:
            if self.debug:
                tprint(
                    f"Worker_DAQ  {self.dev.name}: pause requested...",
                    ANSI.WHITE,
                )

            # The possible undefined behavior of changing variable '_pause'
            # from out of another thread gets handled acceptably correct in
            # '_do_work()' as per my design.
            self._pause = True

    @Slot()
    def _set_pause_false(self):
        """Only useful in mode :const:`DAQ_TRIGGER.CONTINUOUS`. Unpause
        the worker to resume listening for data. Once :attr:`worker_DAQ` has
        successfully resumed, it will emit :obj:`signal_DAQ_updated()` for every
        DAQ update.

        This method should not be called from another thread.
        """
        if self._DAQ_trigger == DAQ_TRIGGER.CONTINUOUS:
            if self.debug:
                tprint(
                    f"Worker_DAQ  {self.dev.name}: unpause requested...",
                    ANSI.WHITE,
                )

            # The possible undefined behavior of changing variable '_pause'
            # from out of another thread gets handled acceptably correct in
            # '_do_work()' as per my design.
            self._pause = False

    # --------------------------------------------------------------------------
    #   _wake_up
    # --------------------------------------------------------------------------

    @Slot()
    def _wake_up(self):
        """Only useful in mode :const:`DAQ_TRIGGER.SINGLE_SHOT_WAKE_UP`. See the
        description at :meth:`QDeviceIO.wake_up_DAQ`.

        This method can be called from another thread.
        """
        if self._DAQ_trigger == DAQ_TRIGGER.SINGLE_SHOT_WAKE_UP:
            if self.debug:
                tprint(
                    f"Worker_DAQ  {self.dev.name}: wake-up requested...",
                    ANSI.WHITE,
                )

            self._qwc.wakeAll()


# ------------------------------------------------------------------------------
#   Worker_jobs
# ------------------------------------------------------------------------------


class Worker_jobs(QtCore.QObject):
    """An instance of this worker will be created and placed inside a new thread
    when :meth:`QDeviceIO.create_worker_jobs` gets called. See there for
    extended information.

    Args:
        qdev (:class:`QDeviceIO`):
            Reference to the parent :class:`QDeviceIO` class instance,
            automatically set when being initialized by
            :meth:`QDeviceIO.create_worker_jobs`.

        jobs_function (:obj:`Callable` | :obj:`None`, optional):

            Default: :obj:`None`.

        debug (:obj:`bool`, optional):

            Default: :const:`False`.

        **kwargs:
            All remaining keyword arguments will be passed onto inherited class
            :class:`PySide6.QtCore.QObject`.

    .. rubric:: Attributes:

    Attributes:
        qdev (:class:`QDeviceIO`):
            Reference to the parent :class:`QDeviceIO` class instance.

        dev (:obj:`object` | :obj:`None`):
            Reference to the user-supplied *device* class instance containing
            I/O methods, automatically set when calling
            :meth:`QDeviceIO.create_worker_jobs`. It is a shorthand for
            :obj:`self.qdev.dev`.

        jobs_function (:obj:`Callable` | :obj:`None`):
            See :meth:`QDeviceIO.create_worker_jobs`.
    """

    def __init__(
        self,
        qdev: QDeviceIO,
        jobs_function: Union[Callable, None] = None,
        debug: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)  # Pass **kwargs onto QtCore.QObject()
        self.debug = debug
        self.debug_color = ANSI.YELLOW

        self.qdev = qdev
        self.dev = _NoDevice() if qdev is None else qdev.dev

        self.jobs_function = jobs_function
        self._has_started = False
        self._has_stopped = False

        self._running = True
        self._qwc = QtCore.QWaitCondition()
        self._mutex_wait = QtCore.QMutex()

        # Use a 'sentinel' value to signal the start and end of the queue
        # to ensure proper multithreaded operation.
        self._sentinel = None
        self._queue = queue.Queue()
        self._queue.put(self._sentinel)

        if self.debug:
            tprint(
                f"Worker_jobs {self.dev.name}: "
                f"init @ thread {_cur_thread_name()}",
                self.debug_color,
            )

    # --------------------------------------------------------------------------
    #   _do_work
    # --------------------------------------------------------------------------

    @_coverage_resolve_trace
    @Slot()
    def _do_work(self):
        # fmt: off
        # Uncomment block to enable Visual Studio Code debugger to have access
        # to this thread. DO NOT LEAVE BLOCK UNCOMMENTED: Running it outside of
        # the debugger causes crashes.
        """
        if self.debug:
            import pydevd
            pydevd.settrace(suspend=False)
        """
        # fmt: on

        init = True

        def confirm_has_started(self):
            # Wait a tiny amount of extra time for QDeviceIO to have entered
            # 'self._qwc_worker_###_started.wait(self._mutex_wait_worker_###)'
            # of method 'start_worker_###()'.
            time.sleep(0.05)

            if self.debug:
                tprint(
                    f"Worker_jobs {self.dev.name}: has started",
                    self.debug_color,
                )

            # Send confirmation
            self.qdev._qwc_worker_jobs_started.wakeAll()
            self._has_started = True

        if self.debug:
            tprint(
                f"Worker_jobs {self.dev.name}: "
                f"starting @ thread {_cur_thread_name()}",
                self.debug_color,
            )

        locker_wait = QtCore.QMutexLocker(self._mutex_wait)
        locker_wait.unlock()

        while self._running:
            locker_wait.relock()

            if self.debug:
                tprint(
                    f"Worker_jobs {self.dev.name}: waiting for wake-up trigger",
                    self.debug_color,
                )

            if init:
                confirm_has_started(self)
                init = False

            self._qwc.wait(self._mutex_wait)

            if self.debug:
                tprint(
                    f"Worker_jobs {self.dev.name}: has woken up",
                    self.debug_color,
                )

            # Needed check to prevent _perform_jobs() at final wake up
            # when _stop() has been called
            if self._running:
                self._perform_jobs()

            locker_wait.unlock()

        if self.debug:
            tprint(
                f"Worker_jobs {self.dev.name}: has stopped",
                self.debug_color,
            )

        # Wait a tiny amount for the other thread to have entered the
        # QWaitCondition lock, before giving a wakingAll().
        QtCore.QTimer.singleShot(
            100,
            self.qdev._qwc_worker_jobs_stopped.wakeAll,
        )
        self._has_stopped = True

    # --------------------------------------------------------------------------
    #   _perform_jobs
    # --------------------------------------------------------------------------

    @_coverage_resolve_trace
    @Slot()
    def _perform_jobs(self):
        locker = QtCore.QMutexLocker(self.dev.mutex)
        self.qdev.update_counter_jobs += 1

        if self.debug:
            tprint(
                f"Worker_jobs {self.dev.name}: "
                f"lock   # {self.qdev.update_counter_jobs}",
                self.debug_color,
            )

        # Process all jobs until the queue is empty. We must iterate 2 times
        # because we use a sentinel in a FIFO queue. First iter removes the old
        # sentinel. Second iter processes the remaining queue items and will put
        # back a new sentinel again.
        for _i in range(2):
            for job in iter(self._queue.get_nowait, self._sentinel):
                func = job[0]
                args = job[1:]

                if self.debug:
                    if isinstance(func, str):
                        tprint(
                            f"Worker_jobs {self.dev.name}: "
                            f"{func} "
                            f"{args}",
                            self.debug_color,
                        )
                    else:
                        tprint(
                            f"Worker_jobs {self.dev.name}: "
                            f"{func.__name__} "
                            f"{args}",
                            self.debug_color,
                        )

                if self.jobs_function is None:
                    if callable(func):
                        # Default job processing:
                        # Send I/O operation to the device
                        try:
                            func(*args)
                        except Exception as err:  # pylint: disable=broad-except
                            pft(err)
                            dprint(
                                f"@ Worker_jobs {self.dev.name}\n",
                                ANSI.RED,
                            )
                    else:
                        # `func` can not be called. Illegal.
                        pft(f"Received a job that is not a callable: {func}.")
                        dprint(
                            f"@ Worker_jobs {self.dev.name}\n",
                            ANSI.RED,
                        )

                else:
                    # User-supplied job processing
                    self.jobs_function(func, args)

            # Put sentinel back in
            self._queue.put(self._sentinel)

        if self.debug:
            tprint(
                f"Worker_jobs {self.dev.name}: "
                f"unlock # {self.qdev.update_counter_jobs}",
                self.debug_color,
            )

        locker.unlock()
        self.qdev.signal_jobs_updated.emit()

    # --------------------------------------------------------------------------
    #   _stop
    # --------------------------------------------------------------------------

    @Slot()
    def _stop(self):
        """Stop the worker to prepare for quitting the worker thread"""
        if self.debug:
            tprint(
                f"Worker_jobs {self.dev.name}: stopping",
                self.debug_color,
            )

        self._running = False
        self._qwc.wakeAll()  # Wake up for the final time

    # --------------------------------------------------------------------------
    #   _send
    # --------------------------------------------------------------------------

    def _send(self, instruction, pass_args=()):
        """See the description at :meth:`QDeviceIO.send`.

        This method can be called from another thread.
        """
        self._add_to_queue(instruction, pass_args)
        self._process_queue()

    # --------------------------------------------------------------------------
    #   _add_to_queue
    # --------------------------------------------------------------------------

    def _add_to_queue(self, instruction, pass_args=()):
        """See the description at :meth:`QDeviceIO.add_to_jobs_queue`.

        This method can be called from another thread.
        """
        if not isinstance(pass_args, tuple):
            pass_args = (pass_args,)
        self._queue.put((instruction, *pass_args))

    # --------------------------------------------------------------------------
    #   _process_queue
    # --------------------------------------------------------------------------

    def _process_queue(self):
        """See the description at :meth:`QDeviceIO.process_jobs_queue`.

        This method can be called from another thread.
        """
        if self.debug:
            tprint(
                f"Worker_jobs {self.dev.name}: wake-up requested...",
                ANSI.WHITE,
            )

        self._qwc.wakeAll()


# ------------------------------------------------------------------------------
#   Singletons
# ------------------------------------------------------------------------------

# fmt: off
Uninitialized_Worker_DAQ = Worker_DAQ(None)  # pyright: ignore [reportArgumentType]
"""Singleton to compare against to test for an uninitialized `Worker_DAQ`
instance."""
# fmt: on

# fmt: off
Uninitialized_Worker_jobs = Worker_jobs(None)  # pyright: ignore [reportArgumentType]
"""Singleton to compare against to test for an uninitialized `Worker_jobs`
instance."""
# fmt: on
