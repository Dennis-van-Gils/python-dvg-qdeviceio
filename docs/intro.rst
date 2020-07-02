What is it about?
===================

*Hassle-free PyQt5 interface for multithreaded data acquisition and communication with an I/O device.*

Features
--------

    * Build on top of the excellent `Qt5 <https://doc.qt.io/qt-5/>`_
      framework.

    * No in-depth knowledge is needed on multithreading to get started.

    * It will manage the creation and handling of the threads, workers,
      signals and mutexes -- all necessary components for proper multithreading --
      *for you*, reducing it to just a few simple method calls of a
      :class:`~dvg_qdeviceio.QDeviceIO` class instance to get set up and going.

    * Different modes of data-acquisition are available:
        - periodic to a fixed clock
        - synchronized across multiple devices
        - aperiodic -- triggered by specific events
        - continuous -- for high-speed buffered applications
        
    TODO: Extend section

Installation
------------

::
   
    pip install dvg-qdeviceio