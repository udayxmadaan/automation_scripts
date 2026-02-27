# v3.py — Thorlabs Kinesis KCube DC Servo control (pythonnet)
import sys
import time
import os
import argparse
import importlib

try:
    import clr
except Exception:
    print("ERROR: pythonnet (clr) is not available. Install with: pip install pythonnet")
    raise

from System import Decimal

def mm(x) -> Decimal:
    # safest way to make a .NET Decimal (avoid float precision issues)
    return Decimal(str(x))


def run(serial: str, kinesis_path: str = r"C:\Program Files\Thorlabs\Kinesis"):
    # Ensure Kinesis installation path is on sys.path
    if not os.path.isdir(kinesis_path):
        print(f"WARNING: Kinesis path not found: {kinesis_path}")
        print("If Kinesis is installed elsewhere, pass --kinesis-path accordingly.")
    else:
        if kinesis_path not in sys.path:
            sys.path.append(kinesis_path)

    # --- Load assemblies ---
    try:
        clr.AddReference("Thorlabs.MotionControl.DeviceManagerCLI")
        clr.AddReference("Thorlabs.MotionControl.GenericMotorCLI")
        clr.AddReference("Thorlabs.MotionControl.KCube.DCServoCLI")
    except Exception as e:
        print("ERROR: Failed to add Thorlabs assemblies. Ensure Kinesis is installed and the path is correct.")
        raise

    from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI
    from Thorlabs.MotionControl.KCube.DCServoCLI import KCubeDCServo

    # Import Settings module more robustly
    Settings = None
    try:
        Settings = importlib.import_module("Thorlabs.MotionControl.GenericMotorCLI.Settings")
    except Exception:
        # fallback: try top-level import
        try:
            import Thorlabs.MotionControl.GenericMotorCLI.Settings as Settings  # type: ignore
        except Exception:
            Settings = None

    device = None
    try:
        # Find devices
        DeviceManagerCLI.BuildDeviceList()

        # Create and connect device
        device = KCubeDCServo.CreateKCubeDCServo(serial)
        if device is None:
            raise RuntimeError(f"Device with serial {serial} not found or could not be created")

        device.Connect(serial)

        # Wait for settings
        device.WaitForSettingsInitialized(5000)

        # Load motor configuration so MoveTo() can work (units/conversion/settings)
        if Settings is not None:
            try:
                device.LoadMotorConfiguration(
                    serial,
                    Settings.DeviceConfiguration.DeviceSettingsUseOptionType.UseFileSettings,
                )
            except Exception as e:
                print("WARNING: LoadMotorConfiguration failed:", repr(e))
                try:
                    names = [n for n in dir(Settings) if "Device" in n or "Config" in n or "Settings" in n]
                    print("Settings module names (filtered):", names)
                except Exception:
                    pass
        else:
            print("WARNING: Settings module not available; skipping LoadMotorConfiguration")

        # Enable + polling
        device.StartPolling(250)
        device.EnableDevice()
        time.sleep(0.5)

        # Home once
        print("Homing...")
        try:
            import threading

            home_ex = []

            def _do_home():
                try:
                    device.Home(60000)
                except Exception as e:
                    home_ex.append(e)

            t = threading.Thread(target=_do_home, daemon=True)
            t.start()
            # join briefly so we don't block the main thread indefinitely
            t.join(10)
            if t.is_alive():
                print("Home() is still running after 10s; continuing with polling to detect homed state...")
            else:
                if home_ex:
                    print("WARNING: Home() raised:", repr(home_ex[0]))
                else:
                    print("Home() returned")

        except Exception as e:
            print("WARNING: Home() invocation failed:", repr(e))

        print("Home command sent, waiting for homing to complete (max 60s)...")
        homed = False
        start_t = time.time()
        timeout = 60.0
        while time.time() - start_t < timeout:
            time.sleep(0.5)
            # probe common homed-related attributes/methods on the device
            for attr in ("IsHomed", "IsHoming", "IsDeviceHomed", "IsHomedState"):
                try:
                    a = getattr(device, attr)
                    val = a() if callable(a) else a
                    print(f"DEBUG {attr} = {val}")
                    if val:
                        homed = True
                        break
                except Exception:
                    pass
            if homed:
                break
        print(f"Homing complete? {homed}")

        # ---- BASIC MOVES (absolute positions, in mm if stage settings are correct) ----
        print("Move forward to 2 mm")
        try:
            device.MoveTo(mm(2), 60000)
            print("MoveTo(2) called")
        except Exception as e:
            print("ERROR: MoveTo(2) raised:", repr(e))
        time.sleep(0.5)

        print("Move backward to 1 mm")
        try:
            device.MoveTo(mm(1), 60000)
            print("MoveTo(1) called")
        except Exception as e:
            print("ERROR: MoveTo(1) raised:", repr(e))
        time.sleep(0.5)

        print("Move back to 0 mm")
        try:
            device.MoveTo(mm(0), 60000)
            print("MoveTo(0) called")
        except Exception as e:
            print("ERROR: MoveTo(0) raised:", repr(e))

        print("Done.")

    finally:
        # Shutdown cleanly
        if device is not None:
            try:
                device.StopPolling()
            except Exception:
                pass
            try:
                device.ShutDown()
            except Exception:
                pass


def parse_args():
    p = argparse.ArgumentParser(description="KCube DC Servo simple mover")
    p.add_argument("--serial", "-s", default="27501283", help="Device serial number")
    p.add_argument("--kinesis-path", default=r"C:\Program Files\Thorlabs\Kinesis", help="Kinesis install path")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(args.serial, args.kinesis_path)