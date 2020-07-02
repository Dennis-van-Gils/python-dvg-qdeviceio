.. py:module:: dvg_qdeviceio

Useful notes
============

Timestamping
------------
    
There are two common approaches to register a timestamp to a
reading. Either one can rely on a software timer of the master PC --
suggested: :func:`python:time.perf_counter` -- and log a timestamp inside
of your :attr:`~Worker_DAQ.DAQ_function` routine. Or one could rely on a
hardware timer build into the I/O device and have this timestamp
additionally being send back to the PC together with the other requested
readings. In general, the latter is superior in high-speed
applications. There are pros and cons to each of these approaches, which
is a topic in itself and will not be discussed here.

Increase process priority
-------------------------

Snippet::

    import psutil
    
    # Set priority of this process to maximum in the operating system
    print("PID: %s\n" % os.getpid())
    try:
        proc = psutil.Process(os.getpid())
        if os.name == "nt":  # Windows
            proc.nice(psutil.REALTIME_PRIORITY_CLASS)  
        else:                # Other
            proc.nice(-20)   
    except:
        print("Warning: Could not set process to maximum priority.\n")