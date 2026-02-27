# v6.py — KCube DC Servo: robust LoadMotorConfiguration + proper Decimal for MoveTo
import clr
import sys
import time

sys.path.append(r"C:\Program Files\Thorlabs\Kinesis")

clr.AddReference("Thorlabs.MotionControl.DeviceManagerCLI")
clr.AddReference("Thorlabs.MotionControl.GenericMotorCLI")
clr.AddReference("Thorlabs.MotionControl.KCube.DCServoCLI")

from System import Decimal
from System.Globalization import CultureInfo
import Thorlabs.MotionControl.DeviceManagerCLI as DM

from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI
from Thorlabs.MotionControl.KCube.DCServoCLI import KCubeDCServo

serial = "27501283"  # your device

INV = CultureInfo.InvariantCulture

def dec(x) -> Decimal:
    """
    Make a System.Decimal that pythonnet will pass to MoveTo(System.Decimal, int).
    - Decimal(2) works for ints
    - for floats/strings, use Decimal.Parse with invariant culture
    """
    if isinstance(x, int):
        return Decimal(x)
    return Decimal.Parse(str(x), INV)

def try_load_motor_configuration(device, serial: str) -> bool:
    """
    Try multiple ways to load motor configuration.
    This is the step that prevents: DeviceSettingsException: Device settings not initialized
    """
    print("Loading motor configuration...")

    # A) Try: DeviceConfiguration.DeviceSettingsUseOptionType.UseFileSettings  (matches Thorlabs C# examples)
    try:
        if hasattr(DM, "DeviceConfiguration"):
            opt = DM.DeviceConfiguration.DeviceSettingsUseOptionType.UseFileSettings
            device.LoadMotorConfiguration(serial, opt)
            print("Loaded config via DM.DeviceConfiguration.DeviceSettingsUseOptionType.UseFileSettings")
            return True
    except Exception as e:
        print("  - Attempt A failed:", type(e).__name__, e)

    # B) Try: DeviceSettingsUseOptionType.UseFileSettings (some versions expose enum directly)
    try:
        if hasattr(DM, "DeviceSettingsUseOptionType"):
            opt = DM.DeviceSettingsUseOptionType.UseFileSettings
            device.LoadMotorConfiguration(serial, opt)
            print("Loaded config via DM.DeviceSettingsUseOptionType.UseFileSettings")
            return True
    except Exception as e:
        print("  - Attempt B failed:", type(e).__name__, e)

    # C) Try overload with no enum: LoadMotorConfiguration(serial)
    try:
        device.LoadMotorConfiguration(serial)
        print("Loaded config via LoadMotorConfiguration(serial) overload")
        return True
    except Exception as e:
        print("  - Attempt C failed:", type(e).__name__, e)

    print("WARNING: Could not load motor configuration from Python.")
    print("If MoveTo still says 'Device settings not initialized', open Kinesis GUI once,")
    print("confirm Actuator = Z825, then Save/Persist settings, close GUI, and rerun.")
    return False

# 1) Build device list
DeviceManagerCLI.BuildDeviceList()

# 2) Print detected devices
serials = list(DeviceManagerCLI.GetDeviceList())
print("Devices detected by Kinesis:", serials)
if serial not in serials:
    raise RuntimeError(f"Serial {serial} not detected. Detected: {serials}")

device = None
try:
    device = KCubeDCServo.CreateKCubeDCServo(serial)
    if device is None:
        raise RuntimeError("CreateKCubeDCServo returned None (wrong device type or bad serial).")

    device.Connect(serial)
    print("Connected")

    # blocks execution until controller finishes loading its internal config from firmware
    # so commands don't run before the device is ready
    device.WaitForSettingsInitialized(5000)

    # IMPORTANT: load motor config so MoveTo has unit converter/settings
    try_load_motor_configuration(device, serial)

    # starts a background thread that continuously queries the device for status updates 
    # on things like position
    device.StartPolling(250)
    device.EnableDevice() # enables motor drive electronics
    time.sleep(0.75) # prevent race conditions
    
    print("Moving to a reference point to define 0 accurately...")
    device.Home(60000)

    print("Move to 2.0 mm")
    device.MoveTo(dec(2.0), 60000)

    print("Move to 0.0 mm")
    device.MoveTo(dec(0.0), 60000)

    print("Done.")

finally:
    if device is not None:
        try:
            device.StopPolling() # stop the start polling thread
        except Exception:
            pass
        try:
            device.ShutDown()
        except Exception:
            pass