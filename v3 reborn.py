import sys
import time
import clr
from System import Decimal, Int32

sys.path.append(r"C:\Program Files\Thorlabs\Kinesis")

clr.AddReference("Thorlabs.MotionControl.DeviceManagerCLI")
clr.AddReference("Thorlabs.MotionControl.GenericMotorCLI")
clr.AddReference("Thorlabs.MotionControl.KCube.DCServoCLI")

from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI
from Thorlabs.MotionControl.KCube.DCServoCLI import KCubeDCServo

serialNo = "27501283"

DeviceManagerCLI.BuildDeviceList()
device = KCubeDCServo.CreateKCubeDCServo(serialNo)

device.Connect(serialNo)
device.WaitForSettingsInitialized(5000)
device.LoadMotorConfiguration(serialNo)

device.StartPolling(250)

device.EnableDevice()
time.sleep(1.0)  # give enable time to latch

device.Home(60000)

timeout = Int32(60000)

def ensure_enabled():
    # Some firmwares expose IsEnabled; if yours doesn't, this still works safely
    try:
        if not device.IsEnabled:
            device.EnableDevice()
            time.sleep(0.5)
    except Exception:
        # If IsEnabled isn't available, just enable anyway
        device.EnableDevice()
        time.sleep(0.5)

def move_by_mm(delta_mm_int: int):
    ensure_enabled()
    cur = device.Position
    device.MoveTo(cur + Decimal(delta_mm_int), timeout)
    time.sleep(0.2)  # small settle/polling update time

device.Home(60000)
time.sleep(0.2)  # small settle/polling update time
move_by_mm(5)
move_by_mm(2)
move_by_mm(-1)

device.StopPolling()
device.ShutDown()

print("Done.")