import clr
import sys
import time

# Path to Kinesis DLLs
sys.path.append(r"C:\Program Files\Thorlabs\Kinesis")

# Load required assemblies
clr.AddReference("Thorlabs.MotionControl.DeviceManagerCLI")
clr.AddReference("Thorlabs.MotionControl.GenericMotorCLI")
clr.AddReference("Thorlabs.MotionControl.KCube.DCServoCLI")

from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI
from Thorlabs.MotionControl.KCube.DCServoCLI import KCubeDCServo

# --------- YOUR DEVICE SERIAL NUMBER ----------
serial = "27000423"   # change to your real one
# ---------------------------------------------

# Find devices
DeviceManagerCLI.BuildDeviceList()

# Create and connect device
device = KCubeDCServo.CreateKCubeDCServo(serial)
device.Connect(serial)
device.WaitForSettingsInitialized(5000)

# Enable
device.StartPolling(250)
device.EnableDevice()
time.sleep(0.5)

# Home once
print("Homing...")
device.Home(60000)

# ---- BASIC FORWARD / BACKWARD MOVES ----

print("Move forward to 5 mm")
device.MoveTo(5, 60000)
time.sleep(1)

print("Move backward to 1 mm")
device.MoveTo(1, 60000)
time.sleep(1)

print("Move back to zero")
device.MoveTo(0, 60000)

# Shutdown cleanly
device.StopPolling()
device.ShutDown()

print("Done.")
