#!/usr/bin/env python3
"""
stage_frontend.py

A simple MIDAS slow-control frontend/client for a Thorlabs Kinesis stage.

What it does:
- Connects to MIDAS as client "stage_fe"
- Creates ODB keys under /Equipment/Stage
- Connects to the Kinesis stage using your kinesis_stage.py
- Polls ODB for commands like HOME, MOVE_ABS, MOVE_REL, ENABLE, DISABLE
- Updates current position, busy state, and errors back into ODB

Expected kinesis_stage.py functions:
    setup(serialNo) -> (device, timeout)
    ensure_enabled(device)
    move_relative(delta_mm_int, device, timeout)
    move_absolute(position_mm, device, timeout)
    homing(device)
    turnoff(device)
    position(device) -> numeric position in mm

Important:
- Remove any example code at the bottom of kinesis_stage.py so import does not move hardware.
- This is a polling slow-control client. It is a very good first version.
"""

import sys
import time
import traceback
from typing import Optional

# MIDAS python client
import midas.client

# Your hardware driver
import kinesis_stage


CLIENT_NAME = "stage_fe"
EQUIPMENT_NAME = "Stage"
ODB_BASE = f"/Equipment/{EQUIPMENT_NAME}"

POLL_SECS = 0.2
POS_UPDATE_SECS = 0.5


class StageFrontend:
    def __init__(self):
        self.client = None
        self.device = None
        self.timeout = None
        self.serial = None

        self.connected = False
        self.enabled = False
        self.busy = False
        self.last_error = ""
        self.last_action = "startup"
        self.last_position = 0.0

        self.last_cmd_id_seen = -1
        self.last_pos_update = 0.0
        self.running = True

    # ----------------------------
    # Lifecycle-ish methods
    # ----------------------------

    def frontend_init(self):
        """Runs once at startup."""
        self.client = midas.client.MidasClient(CLIENT_NAME)
        self._ensure_odb_tree()

        self._set_var("Connected", False)
        self._set_var("Enabled", False)
        self._set_var("Busy", False)
        self._set_var("Error", "")
        self._set_var("Last action", "frontend_init")
        self._set_var("Status", "Initializing")
        self._set_var("Position mm", 0.0)

        self.serial = self._get_set("Serial", "27501283")

        try:
            self.device, self.timeout = kinesis_stage.setup(self.serial)
            self.connected = True
            self.last_action = f"Connected to serial {self.serial}"
            self._set_status("Connected")
            self._publish_state()

            # Optional: auto-enable at startup if desired
            auto_enable = self._get_set("Auto enable on startup", True)
            if auto_enable:
                self._safe_enable()

        except Exception as exc:
            self._record_error(f"frontend_init failed: {exc}")
            raise

    def begin_of_run(self, run_number: Optional[int] = None):
        """Called when a run starts. Here we just refresh state."""
        self.last_action = f"begin_of_run {run_number}"
        self._set_status("Run started")
        self._publish_state()

    def end_of_run(self, run_number: Optional[int] = None):
        """Called when a run stops."""
        self.last_action = f"end_of_run {run_number}"
        self._set_status("Run stopped")
        self._publish_state()

    def pause_run(self, run_number: Optional[int] = None):
        self.last_action = f"pause_run {run_number}"
        self._set_status("Run paused")
        self._publish_state()

    def resume_run(self, run_number: Optional[int] = None):
        self.last_action = f"resume_run {run_number}"
        self._set_status("Run resumed")
        self._publish_state()

    def frontend_exit(self):
        """Runs once when shutting down."""
        try:
            self._set_status("Shutting down")
            if self.device is not None:
                try:
                    kinesis_stage.turnoff(self.device)
                except Exception as exc:
                    self._record_error(f"turnoff failed during exit: {exc}")
        finally:
            self.connected = False
            self.enabled = False
            self.busy = False
            self._publish_state()
            if self.client is not None:
                try:
                    self.client.disconnect()
                except Exception:
                    pass

    def frontend_loop(self):
        """
        Main loop:
        - periodically update position
        - poll ODB for commands
        """
        while self.running:
            try:
                self._maybe_update_position()
                self._check_run_state()
                self._check_command()
            except KeyboardInterrupt:
                self.running = False
                break
            except Exception as exc:
                self._record_error(f"frontend_loop error: {exc}")
                time.sleep(1.0)

            time.sleep(POLL_SECS)

    # ----------------------------
    # MIDAS ODB helpers
    # ----------------------------

    def _odb_path(self, tail: str) -> str:
        return f"{ODB_BASE}/{tail}"

    def _settings_path(self, tail: str) -> str:
        return f"{ODB_BASE}/Settings/{tail}"

    def _vars_path(self, tail: str) -> str:
        return f"{ODB_BASE}/Variables/{tail}"

    def _get(self, path: str, default=None):
        try:
            if self.client.odb_exists(path):
                return self.client.odb_get(path)
            return default
        except Exception:
            return default

    def _set(self, path: str, value):
        self.client.odb_set(path, value)

    def _get_set(self, key: str, default):
        path = self._settings_path(key)
        if not self.client.odb_exists(path):
            self.client.odb_set(path, default)
            return default
        return self.client.odb_get(path)

    def _set_var(self, key: str, value):
        self.client.odb_set(self._vars_path(key), value)

    def _set_status(self, text: str):
        self._set_var("Status", text)

    def _ensure_odb_tree(self):
        # Settings
        defaults = {
            "Serial": "27501283",
            "Auto enable on startup": True,
            "Command": "NONE",
            "Command ID": 0,
            "Target mm": 0.0,
            "Relative mm": 1.0,
            "Poll period ms": int(POLL_SECS * 1000),
            "Position update ms": int(POS_UPDATE_SECS * 1000),
        }

        # Variables
        variables = {
            "Connected": False,
            "Enabled": False,
            "Busy": False,
            "Position mm": 0.0,
            "Error": "",
            "Last action": "",
            "Status": "Booting",
        }

        for k, v in defaults.items():
            if not self.client.odb_exists(self._settings_path(k)):
                self.client.odb_set(self._settings_path(k), v)

        for k, v in variables.items():
            if not self.client.odb_exists(self._vars_path(k)):
                self.client.odb_set(self._vars_path(k), v)

    def _publish_state(self):
        self._set_var("Connected", self.connected)
        self._set_var("Enabled", self.enabled)
        self._set_var("Busy", self.busy)
        self._set_var("Position mm", float(self.last_position))
        self._set_var("Error", self.last_error)
        self._set_var("Last action", self.last_action)

    # ----------------------------
    # Hardware helpers
    # ----------------------------

    def _safe_enable(self):
        if self.device is None:
            raise RuntimeError("Device not connected")
        self.busy = True
        self._publish_state()
        try:
            kinesis_stage.ensure_enabled(self.device)
            self.enabled = True
            self.last_action = "Enabled motor"
            self.last_error = ""
            self._set_status("Enabled")
        finally:
            self.busy = False
            self._publish_state()

    def _safe_disable(self):
        if self.device is None:
            raise RuntimeError("Device not connected")
        self.busy = True
        self._publish_state()
        try:
            kinesis_stage.turnoff(self.device)
            self.enabled = False
            self.last_action = "Disabled motor"
            self.last_error = ""
            self._set_status("Disabled")
        finally:
            self.busy = False
            self._publish_state()

    def _safe_home(self):
        if self.device is None:
            raise RuntimeError("Device not connected")
        self.busy = True
        self._publish_state()
        try:
            kinesis_stage.homing(self.device)
            self.last_action = "Homing complete"
            self.last_error = ""
            self._set_status("Homed")
            self._update_position_now()
        finally:
            self.busy = False
            self._publish_state()

    def _safe_move_abs(self, target_mm: float):
        if self.device is None:
            raise RuntimeError("Device not connected")
        self.busy = True
        self._publish_state()
        try:
            kinesis_stage.move_absolute(float(target_mm), self.device, self.timeout)
            self.last_action = f"Moved absolute to {target_mm:.3f} mm"
            self.last_error = ""
            self._set_status("Move absolute complete")
            self._update_position_now()
        finally:
            self.busy = False
            self._publish_state()

    def _safe_move_rel(self, delta_mm: float):
        if self.device is None:
            raise RuntimeError("Device not connected")
        self.busy = True
        self._publish_state()
        try:
            # Your current function signature says delta_mm_int: int
            # so we round to int here to match your existing driver.
            delta_int = int(round(delta_mm))
            kinesis_stage.move_relative(delta_int, self.device, self.timeout)
            self.last_action = f"Moved relative by {delta_int} mm"
            self.last_error = ""
            self._set_status("Move relative complete")
            self._update_position_now()
        finally:
            self.busy = False
            self._publish_state()

    def _update_position_now(self):
        if self.device is None:
            return
        try:
            self.last_position = float(kinesis_stage.position(self.device))
            self.last_error = ""
        except Exception as exc:
            self._record_error(f"Position read failed: {exc}")
        self.last_pos_update = time.time()
        self._publish_state()

    def _maybe_update_position(self):
        now = time.time()
        update_secs = max(0.05, self._get(self._settings_path("Position update ms"), 500) / 1000.0)
        if now - self.last_pos_update >= update_secs:
            self._update_position_now()

    # ----------------------------
    # Command handling
    # ----------------------------

    def _check_command(self):
        cmd_id = int(self._get(self._settings_path("Command ID"), 0))
        if cmd_id == self.last_cmd_id_seen:
            return

        cmd = str(self._get(self._settings_path("Command"), "NONE")).strip().upper()
        self.last_cmd_id_seen = cmd_id

        if cmd == "NONE":
            return

        self.client.msg(f"{CLIENT_NAME}: received command {cmd} (Command ID {cmd_id})")

        try:
            if cmd == "ENABLE":
                self._safe_enable()

            elif cmd == "DISABLE":
                self._safe_disable()

            elif cmd == "HOME":
                self._safe_home()

            elif cmd == "MOVE_ABS":
                target = float(self._get(self._settings_path("Target mm"), 0.0))
                self._safe_move_abs(target)

            elif cmd == "MOVE_REL":
                delta = float(self._get(self._settings_path("Relative mm"), 0.0))
                self._safe_move_rel(delta)

            elif cmd == "RECONNECT":
                self._reconnect()

            elif cmd == "QUIT":
                self.running = False
                self.last_action = "QUIT requested"
                self._set_status("Stopping frontend")

            else:
                raise ValueError(f"Unknown command: {cmd}")

            # Clear the command after successful handling
            self._set(self._settings_path("Command"), "NONE")

        except Exception as exc:
            self._record_error(f"Command {cmd} failed: {exc}")

    def _reconnect(self):
        self.busy = True
        self._publish_state()
        try:
            if self.device is not None:
                try:
                    kinesis_stage.turnoff(self.device)
                except Exception:
                    pass

            self.device, self.timeout = kinesis_stage.setup(self.serial)
            self.connected = True
            self.last_action = "Reconnected"
            self.last_error = ""
            self._set_status("Reconnected")
            self._update_position_now()
        finally:
            self.busy = False
            self._publish_state()

    def _record_error(self, text: str):
        self.last_error = text
        self.last_action = "ERROR"
        self._set_status("Error")
        self._publish_state()
        if self.client is not None:
            try:
                self.client.msg(f"{CLIENT_NAME}: {text}", is_error=True)
            except Exception:
                pass
        print(text, file=sys.stderr)
        traceback.print_exc()

    # ----------------------------
    # Optional run-state integration
    # ----------------------------

    def _check_run_state(self):
        """
        Optional: watch /Runinfo/State and call lifecycle-style methods.

        MIDAS setups differ a bit in how this is used, so this is intentionally simple.
        If you don't care about run transitions for the stage, you can leave this alone.
        """
        state = self._get("/Runinfo/State", None)
        if not hasattr(self, "_last_run_state"):
            self._last_run_state = state
            return

        if state == self._last_run_state:
            return

        old_state = self._last_run_state
        self._last_run_state = state

        # These integer values can vary by setup/version,
        # so we keep the logic conservative and log the change.
        self.client.msg(f"{CLIENT_NAME}: Run state changed {old_state} -> {state}")

        # A very light-touch policy:
        # - just note transitions
        # - do not automatically move hardware on run start/stop
        if state is not None:
            if str(state) == "1":
                self.begin_of_run()
            elif str(state) == "3":
                self.pause_run()
            elif old_state is not None and str(old_state) == "3" and str(state) == "2":
                self.resume_run()
            elif str(state) == "2":
                # often "running" in some setups
                pass
            elif str(state) == "0":
                self.end_of_run()


def main():
    fe = StageFrontend()

    try:
        fe.frontend_init()
        fe.client.msg(f"{CLIENT_NAME}: started")
        fe.frontend_loop()
    except KeyboardInterrupt:
        print("KeyboardInterrupt: exiting")
    except Exception as exc:
        print(f"Fatal error: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
    finally:
        fe.frontend_exit()


if __name__ == "__main__":
    main()