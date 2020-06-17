Changelog
=========

0.0.1 (2020-05-25)
------------------
* First release on PyPI.

0.0.5 (2020-06-06)
------------------
* Implemented smooth start and stop machinery to the workers.

0.0.6 (2020-06-07)
------------------
* Added start(), renamed quit_all_workers() to quit()
* Added send(), add_to_send_queue(), process_send_queue()

0.0.8 (2020-06-09)
------------------
* Added pause_DAQ, unpause_DAQ(), wake_up_DAQ()
* Changed many attribute and method names
* Code style: black

0.0.9 (2020-06-17)
------------------
* Moved the Worker_### classes outside of QDeviceIO and into module root
* Added documentation using Sphinx and Read the docs
* Changed from MarkDown to ReStructuredText