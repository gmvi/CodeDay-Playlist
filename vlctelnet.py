import telnetlib

class VLCTelnet():
    telnet = None
    
    def __init__(self, host="localhost", port=4212, password="admin"):
        self.telnet = telnetlib.Telnet(host="localhost", port=4212)
        self.telnet.read_until("Password: ", timeout = 2)
        self.telnet.write(password+"\r\n")
        self.telnet.read_until("> ", timeout = 2)
        
    def cmd(self, string):
        self.telnet.write(string+"\r\n")
        NEWLINES = ["\r", "\n"]
        b = "\r\n"
        while b != "" and b[-1:] in NEWLINES:
                b = self.telnet.read_until("\r\n", timeout=1)
                print b.strip()
