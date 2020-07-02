Usage
==============

Step 0
--------------

TODO: Mention it must be running inside a
:class:`PyQt5.QtCore.QCoreApplication` or
:class:`PyQt5.QtWidgets.QApplication`!
    
Step 1
--------------

Create a QDeviceIO instance and pass it your *device* class instance (not
included, you have to write it yourself) containing general I/O methods, 
such as receiving, parsing and sending instructions directly to the
peripheral I/O device.

   ::
        
    from dvg_qdeviceio import QDeviceIO, DAQ_trigger
   
    dev = My_device()
    dev.connect(115200, "COM1")
    
    qdev = QDeviceIO(dev)

   Where ``My_device()`` could look like this in case it uses the serial
   communication protocol (pseudo-code)::
   
    import serial  # https://pyserial.readthedocs.io/en/latest/pyserial.html
   
    class My_device(object):
        def __init__(self, ...):
            self.ser = None                  # Will hold the serial connection
            self.is_alive = False            # Is the connection up?
        
        def connect(self, baudrate, port_str) -> bool:
            try:
                self.ser = serial.Serial(port=port_str, baudrate=baudrate)
                self.is_alive = True         # Connection established
                return True                  # Successful
            except serial.SerialException:
                print("Could not open port")
                return False
            except:
                raise
        
        def write(self, instruction) -> bool:
            try:
                self.ser.write(instruction.encode())
                return True                  # Successful
            except:
                print("I/O error")
                return False
            
        def query(self, instruction) -> [bool, str]:
            if self.write(instruction):
                try:
                    ans_bytes = self.ser.read_until('\n'.encode())
                ...
                
                try:
                    ans_str = ans_bytes.decode('utf8').strip()
                ...
                
                return [success, ans_str]
                
        etc...
        
2) Create and configure the workers you need in one or two lines of code.

3) Pass it references to your functions containing your specific DAQ &
   data processing routines, and/or your specific outgoing instructions you
   wish to send to the I/O device.
   
4) Start the workers.
   
The functions of step 3 will then be handled in a multithreaded fashion *for
you*.

TODO: Extend section