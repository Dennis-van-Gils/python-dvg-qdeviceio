.. py:module:: dvg_qdeviceio
.. _`INTERNAL_TIMER`:

DAQ_TRIGGER.INTERNAL_TIMER
----------------------------------

.. figure:: DAQ_trigger_diagram.png
    :target: _images/DAQ_trigger_diagram.png
    :alt: DAQ_trigger diagram

    Typical use-cases for the different :class:`DAQ_TRIGGER` modes of
    :class:`Worker_DAQ`. Variations are possible.

Internal to the :class:`Worker_DAQ` class instance will be a software
timer of type :class:`PyQt5.QtCore.QTimer` that will periodically tick,
see the above diagram. Every *tick* of the timer
will trigger an *update* in :class:`Worker_DAQ`; make it perform a
single execution of its :attr:`~Worker_DAQ.DAQ_function` member.

Typically, the :attr:`~Worker_DAQ.DAQ_function` could instruct the
device to report back on a requested quantity: a so-called *query*
operation. In this case, the PC is acting as a master to the peripheral
I/O device. Either the requested quantity still needs to get
measured by the device and, hence, there is a delay before the
device can reply. Or the requested quantity was already measured
and only has to be retreived from a memory buffer on the device. The
latter is faster.

Example::

    from dvg_qdeviceio import QDeviceIO, DAQ_TRIGGER

    qdev = QDeviceIO(my_device)
    qdev.create_worker_DAQ(
        DAQ_trigger     = DAQ_TRIGGER.INTERNAL_TIMER,
        DAQ_function    = my_DAQ_function,
        DAQ_interval_ms = 10,  # 10 ms --> 100 Hz
    )
    qdev.start()

.. Attention::

    The typical maximum granularity of :class:`PyQt5.QtCore.QTimer` is
    around ~1 ms, depending on the operating system.