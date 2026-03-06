import sys
import time
import clr

sys.path.append(r"C:\Program Files\Thorlabs\Kinesis")

clr.AddReference("Thorlabs.MotionControl.DeviceManagerCLI")
clr.AddReference("Thorlabs.MotionControl.GenericMotorCLI")
clr.AddReference("Thorlabs.MotionControl.KCube.DCServoCLI")

from System import Decimal, Int32
from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI
from Thorlabs.MotionControl.KCube.DCServoCLI import KCubeDCServo

def setup(serialNo):
    print("Script Run")
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

    return device, timeout

def ensure_enabled(device):
    # Some firmwares expose IsEnabled; if yours doesn't, this still works safely
    try:
        if not device.IsEnabled:
            device.EnableDevice()
            time.sleep(0.5)
    except Exception:
        # If IsEnabled isn't available, just enable anyway
        device.EnableDevice()
        time.sleep(0.5)

def move_relative(delta_mm_int: int, device, timeout):
    ensure_enabled()
    cur = device.Position
    device.MoveTo(cur + Decimal(delta_mm_int), timeout)
    time.sleep(0.2)  # small settle/polling update time

def move_absolute(position_mm: float, device, timeout):
    # Ensure device is enabled
    try:
        if not device.IsEnabled:
            device.EnableDevice()
            time.sleep(0.5)
    except:
        device.EnableDevice()
        time.sleep(0.5)

    target = Decimal(position_mm)
    device.MoveTo(target, timeout)

def homing(device):
    device.Home(60000)
    time.sleep(0.2)  # small settle/polling update time

def turnoff(device):
    device.StopPolling()
    device.ShutDown()

def position(device):
    return device.Position

# example 
serialNo = "27501283"
device, timeout = setup(serialNo) #setup
homing(device) # home to set reference
move_absolute(5, device, timeout) # absolute or relative movement functions can be called
move_relative(2, device, timeout)
print(position(device))
turnoff(device) # turn off motor (stop polling & shutdown)
print("Done.") 