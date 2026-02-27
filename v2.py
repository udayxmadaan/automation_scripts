# v5.py — robust connect + list devices first (KCube DC Servo)
import clr
import sys
import time
from System import Decimal

sys.path.append(r"C:\Program Files\Thorlabs\Kinesis")

clr.AddReference("Thorlabs.MotionControl.DeviceManagerCLI")
clr.AddReference("Thorlabs.MotionControl.GenericMotorCLI")
clr.AddReference("Thorlabs.MotionControl.KCube.DCServoCLI")

from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI
from Thorlabs.MotionControl.KCube.DCServoCLI import KCubeDCServo

serial = "27501283"   # <-- your serial

def dec(x) -> Decimal:
    return Decimal.Parse(str(x))

# 1) Build device list
DeviceManagerCLI.BuildDeviceList()

# 2) Print devices Kinesis can currently see (IMPORTANT)
try:
    # Often this returns a .NET List[String]
    serials = DeviceManagerCLI.GetDeviceList()
    print("Devices detected by Kinesis:", list(serials))
except Exception as e:
    print("Could not query device list:", repr(e))
    serials = []

# 3) Hard fail if your serial isn't detected
if serials and serial not in list(serials):
    raise RuntimeError(
        f"Your serial {serial} is NOT in the detected device list.\n"
        f"Detected: {list(serials)}\n"
        "Fix: unplug/replug USB, power-cycle the cube, close Kinesis GUI, then rerun."
    )

device = None
try:
    # 4) Create device instance
    device = KCubeDCServo.CreateKCubeDCServo(serial)
    if device is None:
        raise RuntimeError("CreateKCubeDCServo returned None (device type mismatch or serial not found).")

    # 5) Connect
    print("Connecting...")
    device.Connect(serial)

    # 6) Wait until settings are initialized
    device.WaitForSettingsInitialized(5000)

    # 7) Start polling + enable
    device.StartPolling(250)
    device.EnableDevice()
    time.sleep(0.75)

    print("Homing...")
    device.Home(60000)

    print("Move to 2 (units depend on your stage settings)")
    device.MoveTo(2.0, 60000)

    print("Move to 0")
    device.MoveTo(0.0, 60000)

    print("Done.")

finally:
    if device is not None:
        try:
            device.StopPolling()
        except Exception:
            pass
        try:
            device.ShutDown()
        except Exception:
            pass