DvG_QDeviceIO
=============

*Hassle-free PyQt/PySide interface for multithreaded data acquisition and
communication with an I/O device.*

It will manage many necessary components for proper multithreading -- creation
and handling of the threads, workers, signals and mutexes -- *for you*, reducing
it to just a few simple method calls of a QDeviceIO class instance to get set up
and going.

- Documentation: https://python-dvg-qdeviceio.readthedocs.io
- Github: https://github.com/Dennis-van-Gils/python-dvg-qdeviceio
- PyPI: https://pypi.org/project/dvg-qdeviceio

Installation::

   pip install dvg-qdeviceio


.. toctree::
   :caption: Introduction

   features
   usage
   example


.. toctree::
   :caption: API

   api-qdeviceio
   api-workerdaq
   api-workerjobs
   api-daqtrigger
   └ INTERNAL_TIMER <api-daqtrigger-internaltimer>
   └ SINGLE_SHOT_WAKE_UP <api-daqtrigger-singleshotwakeup>
   └ CONTINUOUS <api-daqtrigger-continuous>


.. toctree::
   :maxdepth: 1
   :caption: Other

   notes
   authors
   changelog
   contributing
   genindex
