"""Quick serial poke for the servotest firmware: python servo_poke.py <port> <servo 1|2>."""
import sys
import time

import serial

port, n = sys.argv[1], sys.argv[2]
s = serial.Serial(port, 115200, timeout=0.5)
time.sleep(2.2)  # opening resets the Uno
for a in (135, 45, 90):
    s.write(f"{n} {a}\n".encode())
    time.sleep(1.5)
    print(s.read(100).decode().strip())
