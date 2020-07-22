Changelog
=========

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
