Changelog
=========

1.4.0 (2024-06-12)
------------------
Major code quality improvements:

* Using ``qtpy`` library instead of my own Qt5/6 mechanism
* Improved ``_NoDevice`` mechanism
* Removed redundant ``attach_device()``
* Extra check in ``Worker_jobs`` if ``func`` is actually a callable
* Using singletons ``Uninitialized_Worker_DAQ/jobs`` as default attribute
  values instead of using ``None``. This solves pylint warnings on '... is not a
  known attribute of None'.
* Docstring improvement: ``create_worker_DAQ/jobs()`` show full info now
* Docstring improvement: Linking against PySide6, instead of PyQt5
* Improved code quality of the pytest

Potential code breaks:

* Removed Python 3.6 support
* The methods of ``Worker_DAQ`` and ``Worker_jobs`` have been hidden from the
  API and are dundered now. You should not have been calling them anyhow outside
  of this module. Their functionality was and is still available as safer
  methods available at the root level of ``QDeviceIO()``. Specifically::

    Worker_DAQ.pause()        --> Worker_DAQ._set_pause_true()   , should use pause_DAQ()
    Worker_DAQ.unpause()      --> Worker_DAQ._set_pause_untrue() , should use unpause_DAQ()
    Worker_DAQ.wake_up()      --> Worker_DAQ._wake_up()          , should use wake_up_DAQ()
    Worker_jobs.send()        --> Worker_jobs._send()            , should use send()
    Worker_jobs.add_to_queue  --> Worker_jobs._add_to_queue()    , should use add_to_queue()
    Worker_jobs.process_queue --> Worker_jobs._process_queue()   , should use process_queue()

1.3.0 (2024-04-02)
------------------
* Support Python 3.11
* All f-strings
* Type checking via ``isinstance()``, not ``type == ...``

1.2.0 (2023-02-27)
------------------
* Deprecated `requires.io` and `travis`
* Raise ``ImportError`` instead of general ``Exception``

1.1.2 (2022-10-26)
------------------
* Minor refactor of mechanism to support PyQt5, PyQt6, PySide2 and PySide6

1.1.1 (2022-09-14)
------------------
* Forgot to bump requirement ``dvg-debug-functions~=2.2`` to ensure support for
  PyQt5, PyQt6, PySide2 and PySide6

1.1.0 (2022-09-13)
------------------
* Added support for PyQt5, PyQt6, PySide2 and PySide6

1.0.0 (2021-07-02)
------------------
* Stable release, identical to v0.4.0

0.4.0 (2021-05-09)
------------------
* Fixed buggy ``worker_DAQ`` pause and unpause routines in ``CONTINUOUS`` mode

0.3.0 (2020-07-23)
-------------------
* Updated start & stop machinery Workers
* Removed unneccesary lambdas
* Revamped DAQ rate calculation. Init arg ``calc_DAQ_rate_every_N_iter`` got removed.

0.2.2 (2020-07-17)
-------------------
* Traceback will be printed when ``DAQ_function`` raises an internal error.
* Introduced ``Worker_###._has_finished`` to prevent hang when closing workers twice.

0.2.1 (2020-07-15)
-------------------
* Added documentation

0.2.0 (2020-07-07)
-------------------
* ``quit_worker_###()``: Added check to see if thread was already closed, due to a ``lost_connection`` event. This prevents an hanging app during quit.
* Changed name of enum class ``DAQ_trigger`` to ``DAQ_TRIGGER``

0.1.2 (2020-07-04)
-------------------
* Proper use of ``super()``, now passing ``**kwargs`` onto subclass ``QtCore.QObject()``

0.1.1 (2020-07-02)
-------------------
* ``Worker_DAQ`` now stores all init arguments, some as _private

0.1.0 (2020-07-02)
-------------------
* DvG module filenames changed to lowercase
* Nearing full release status

0.0.12 (2020-06-29)
-------------------
* ``INTERNAL_TIMER``: Already instantiate the ``QTimer`` in ``create_worker_DAQ()``, instead of in ``start_worker_DAQ()``
* Changed default ``DAQ_timer_type`` from ``CoarseTimer`` to ``PreciseTimer``
* Added more Sphinx documentation

0.0.11
-------------------
Skipped (I screwed up the versioning)

0.0.10 (2020-06-22)
-------------------
* Major: Changed name ``Worker_send`` to ``Worker_jobs`` and similar
* Added more Sphinx documentation

0.0.9 (2020-06-17)
------------------
* Moved the ``Worker_###()`` classes outside of ``QDeviceIO`` and into module root
* Added documentation using Sphinx and Read the docs
* Changed from MarkDown to ReStructuredText

0.0.8 (2020-06-09)
------------------
* Added ``pause_DAQ``, ``unpause_DAQ()``, ``wake_up_DAQ()``
* Changed many attribute and method names
* Code style: black

0.0.6 (2020-06-07)
------------------
* Added ``start()``, renamed ``quit_all_workers()`` to ``quit()``
* Added ``send()``, ``add_to_send_queue()``, ``process_send_queue()``

0.0.5 (2020-06-06)
------------------
* Implemented smooth start and stop machinery to the workers

0.0.1 (2020-05-25)
------------------
* First release on PyPI
