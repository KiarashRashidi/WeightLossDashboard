"""
Bluetooth background service for the Eufy C1 Smart Scale.
Runs an asyncio event loop inside a daemon thread, keeping Flask thread-safe.
"""
import asyncio
import logging
import threading

from bleak import BleakScanner, BleakClient
from bleak.exc import BleakCharacteristicNotFoundError

logger = logging.getLogger(__name__)

TARGET_NAME = "T9146"
NOTIFY_UUID = "0000fff4-0000-1000-8000-00805f9b34fb"


# --- BIA body-composition formulas (reverse-engineered from Holtek chip used in Eufy C1 / Xiaomi Mi Scale) ---
# Source: https://github.com/wiecosystem/Bluetooth/blob/master/sandbox/huami.health.scale2/body_metrics.py

def _clamp(value, lo, hi):
    return max(lo, min(value, hi))


def _lbm_coefficient(weight, height_cm, age, impedance):
    """Lean Body Mass coefficient — combines height, weight, age, impedance."""
    lbm = (height_cm * 9.058 / 100) * (height_cm / 100)
    lbm += weight * 0.32 + 12.226
    lbm -= impedance * 0.0068
    lbm -= age * 0.0542
    return lbm


def body_composition(weight, impedance, height_cm, age, is_male):
    """
    Returns a dict of body metrics.  Returns None if impedance is invalid.
    Formulas: Holtek BIA chip algorithm (Eufy C1 / Xiaomi Mi Scale family).
    """
    if impedance is None or impedance <= 0:
        return None

    sex = "male" if is_male else "female"
    lbm = _lbm_coefficient(weight, height_cm, age, impedance)

    # --- Body Fat % ---
    if sex == "female" and age <= 49:
        const = 9.25
    elif sex == "female" and age > 49:
        const = 7.25
    else:
        const = 0.8

    if sex == "male" and weight < 61:
        coeff = 0.98
    elif sex == "female" and weight > 60:
        coeff = 1.03 * 0.96 if height_cm > 160 else 0.96
    elif sex == "female" and weight < 50:
        coeff = 1.03 * 1.02 if height_cm > 160 else 1.02
    else:
        coeff = 1.0

    fat_pct = (1.0 - (((lbm - const) * coeff) / weight)) * 100
    if fat_pct > 63:
        fat_pct = 75
    fat_pct = _clamp(fat_pct, 5, 75)

    # --- Water % ---
    water_pct = (100 - fat_pct) * 0.7
    water_coeff = 1.02 if water_pct <= 50 else 0.98
    water_pct = water_pct * water_coeff
    if water_pct >= 65:
        water_pct = 75
    water_pct = _clamp(water_pct, 35, 75)

    # --- Bone Mass (kg) ---
    base = 0.245691014 if sex == "female" else 0.18016894
    bone_mass = (base - lbm * 0.05158) * -1
    bone_mass += 0.1 if bone_mass > 2.2 else -0.1
    if sex == "female" and bone_mass > 5.1:
        bone_mass = 8
    elif sex == "male" and bone_mass > 5.2:
        bone_mass = 8
    bone_mass = _clamp(bone_mass, 0.5, 8)

    # --- Muscle Mass (kg) ---
    muscle_mass = weight - (fat_pct / 100 * weight) - bone_mass
    if sex == "female" and muscle_mass >= 84:
        muscle_mass = 120
    elif sex == "male" and muscle_mass >= 93.5:
        muscle_mass = 120
    muscle_mass = _clamp(muscle_mass, 10, 120)

    # --- BMR (kcal/day) ---
    if sex == "female":
        bmr = 864.6 + weight * 10.2036 - height_cm * 0.39336 - age * 6.204
        if bmr > 2996:
            bmr = 5000
    else:
        bmr = 877.8 + weight * 14.916 - height_cm * 0.726 - age * 8.976
        if bmr > 2322:
            bmr = 5000
    bmr = _clamp(bmr, 500, 10000)

    # --- BMI ---
    bmi = _clamp(weight / ((height_cm / 100) ** 2), 10, 90)

    # --- Visceral Fat index ---
    if sex == "female":
        if weight > (13 - height_cm * 0.5) * -1:
            subsubcalc = (height_cm * 1.45 + height_cm * 0.1158 * height_cm) - 120
            subcalc = weight * 500 / subsubcalc
            vfal = (subcalc - 6) + age * 0.07
        else:
            subcalc = 0.691 + height_cm * -0.0024 + height_cm * -0.0024
            vfal = ((height_cm * 0.027 - subcalc * weight) * -1) + age * 0.07 - age
    else:
        if height_cm < weight * 1.6:
            subcalc = (height_cm * 0.4 - height_cm * (height_cm * 0.0826)) * -1
            vfal = (weight * 305 / (subcalc + 48)) - 2.9 + age * 0.15
        else:
            subcalc = 0.765 + height_cm * -0.0015
            vfal = ((height_cm * 0.143 - weight * subcalc) * -1) + age * 0.15 - 5.0
    visceral_fat = _clamp(vfal, 1, 50)

    # --- Metabolic Age ---
    if sex == "female":
        met_age = (-1.1165 * height_cm + 1.5784 * weight + 0.4615 * age + 0.0415 * impedance + 83.2548)
    else:
        met_age = (-0.7471 * height_cm + 0.9161 * weight + 0.4184 * age + 0.0517 * impedance + 54.2267)
    metabolic_age = _clamp(met_age, 15, 80)

    return {
        "body_fat_pct": round(fat_pct, 1),
        "fat_mass": round(weight * fat_pct / 100, 2),
        "muscle_mass": round(muscle_mass, 2),
        "bone_mass": round(bone_mass, 2),
        "water_pct": round(water_pct, 1),
        "water_kg": round(weight * water_pct / 100, 2),
        "bmr": round(bmr),
        "bmi": round(bmi, 1),
        "visceral_fat": round(visceral_fat, 1),
        "metabolic_age": round(metabolic_age, 1),
    }


def decode_impedance(data):
    if len(data) < 8:
        return None
    pair_56 = (data[6] << 8) | data[5]
    pair_67 = (data[7] << 8) | data[6]
    candidates = []
    for raw in [pair_56, pair_67]:
        for divisor in [10, 50, 100]:
            value = raw / divisor
            if 300 <= value <= 800:
                candidates.append(value)
    if not candidates:
        return None
    return min(candidates, key=lambda x: abs(x - 520))


def decode_packet(data):
    if data == b"\xf3\x00":
        return "finished"
    # T9146 packets are 0xCF-prefixed, at least 10 bytes.
    # data[9] == 0x00 means measurement is stabilized/final (per eufylife-ble-client protocol).
    if len(data) < 10 or data[0] != 0xCF:
        return None
    if data[9] != 0x00:
        return None  # still measuring — not the final reading
    weight_raw = (data[4] << 8) | data[3]
    weight = weight_raw / 100
    if weight < 20 or weight > 250:
        return None
    impedance = decode_impedance(data)
    if impedance is None:
        return None
    return weight, impedance


# --- BluetoothService wraps async bleak in a background thread ---

class BluetoothService:
    def __init__(self, socketio):
        self._socketio = socketio
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._status = "idle"          # idle | scanning | connected | finished | error
        self._latest: dict | None = None
        self._session_params: dict = {}

    # --- Public API (called from Flask routes, runs in Flask thread) ---

    def get_status(self) -> dict:
        return {"status": self._status, "latest": self._latest}

    def get_latest_measurement(self) -> dict | None:
        return self._latest

    def start_scan(self, patient_id=None, height_cm=None, age=None, is_male=True):
        if self._thread and self._thread.is_alive():
            logger.warning("Scan already running, ignoring start_scan().")
            return

        self._session_params = {
            "patient_id": patient_id,
            "height_cm": height_cm,
            "age": age,
            "is_male": is_male,
        }
        self._latest = None
        self._stop_event.clear()
        self._set_status("scanning")

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop_scan(self):
        self._stop_event.set()
        self._set_status("idle")
        logger.info("Bluetooth scan stopped by user.")

    # --- Internal helpers ---

    def _set_status(self, status: str):
        self._status = status
        self._socketio.emit("bluetooth:status", {"status": status})
        logger.info("Bluetooth status: %s", status)

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._scan_and_connect())
        except Exception:
            logger.exception("Fatal error in Bluetooth event loop — restarting is required.")
            self._set_status("error")
        finally:
            self._loop.close()

    async def _scan_and_connect(self):
        logger.info("Starting BLE scan for '%s'...", TARGET_NAME)
        known_address = None  # cached after first scan; avoids re-scanning after services-changed

        while not self._stop_event.is_set():
            try:
                if known_address is None:
                    device = await self._find_device()
                    if device is None:
                        logger.warning("Scale '%s' not found. Retrying in 5s...", TARGET_NAME)
                        await asyncio.sleep(5)
                        continue
                    known_address = device.address
                    target = device
                else:
                    target = known_address  # BleakClient accepts address strings directly

                self._set_status("connected")
                logger.info("Connecting to %s...", known_address)

                services_changed = False

                def _on_services_changed(_):
                    nonlocal services_changed
                    services_changed = True
                    logger.info("GATT services changed on %s — will reconnect immediately.", known_address)

                async with BleakClient(target, timeout=40.0, services_changed_callback=_on_services_changed) as client:
                    # WinRT sometimes returns before GATT table is fully populated;
                    # brief pause + retry prevents intermittent fff4-not-found errors.
                    await asyncio.sleep(1.0)
                    for attempt in range(1, 4):
                        try:
                            await client.start_notify(NOTIFY_UUID, self._on_notification)
                            break
                        except BleakCharacteristicNotFoundError:
                            if attempt == 3:
                                raise
                            logger.warning(
                                "GATT characteristic not ready (attempt %d/3), retrying in 2s...", attempt
                            )
                            await asyncio.sleep(2.0)
                    logger.info("Listening for scale data...")

                    while not self._stop_event.is_set():
                        if not client.is_connected:
                            logger.warning("Scale disconnected unexpectedly.")
                            break
                        await asyncio.sleep(0.5)

                if services_changed:
                    # The scale changed its GATT table (normal pairing transition).
                    # Reconnect to the cached address immediately — no rescan needed.
                    self._set_status("scanning")
                    continue

                # Normal/unexpected disconnect — forget the address and rescan.
                known_address = None

            except Exception:
                logger.exception("BLE error — will retry in 5s.")
                self._set_status("scanning")
                known_address = None
                await asyncio.sleep(5)

        self._set_status("idle")

    async def _find_device(self):
        devices = await BleakScanner.discover(timeout=8.0)
        for d in devices:
            if d.name and TARGET_NAME in d.name:
                return d
        return None

    def _on_notification(self, sender, data: bytearray):
        raw = bytes(data)
        logger.debug("BLE raw packet: %s", raw.hex())
        result = decode_packet(raw)

        if result == "finished":
            # Sentinel fallback — emit finished only if the final weight packet
            # was already captured and we haven't emitted finished yet.
            if self._latest and self._status != "finished":
                logger.info("Scale measurement finished (sentinel).")
                self._set_status("finished")
                self._socketio.emit("bluetooth:finished", self._latest)
            return

        if result is None:
            return

        weight, impedance = result
        p = self._session_params

        metrics = body_composition(
            weight=weight,
            impedance=impedance,
            height_cm=p.get("height_cm") or 170,
            age=p.get("age") or 30,
            is_male=p.get("is_male", True),
        )

        self._latest = {
            "patient_id": p.get("patient_id"),
            "weight": round(weight, 2),
            "impedance": round(impedance, 1),
            **(metrics or {}),
        }

        fat_pct = (metrics or {}).get("body_fat_pct", 0)
        logger.info("BLE data: weight=%.2f kg, body_fat=%.1f%%", weight, fat_pct)
        self._socketio.emit("bluetooth:data", self._latest)
        # Final (stabilized) measurement received — mark complete immediately.
        # Don't wait for the \xf3\x00 sentinel which can arrive late or be missed.
        self._set_status("finished")
        self._socketio.emit("bluetooth:finished", self._latest)
