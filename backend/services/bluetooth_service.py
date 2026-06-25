"""
Bluetooth background service for the Eufy C1 Smart Scale.
Runs an asyncio event loop inside a daemon thread, keeping Flask thread-safe.
"""
import asyncio
import logging
import threading

from bleak import BleakScanner, BleakClient

logger = logging.getLogger(__name__)

TARGET_NAME = "T9146"
NOTIFY_UUID = "0000fff4-0000-1000-8000-00805f9b34fb"


# --- Exact body-composition formulas from project spec ---

def body_composition(weight, impedance, height_cm, age, is_male):
    """Returns (body_fat_pct, water_kg, muscle_kg). Returns (None, None, None) if impedance invalid."""
    if impedance is None or impedance <= 0:
        return None, None, None

    height_m = height_cm / 100
    bmi = weight / (height_m ** 2)

    if is_male:
        body_fat = 1.20 * bmi + 0.23 * age - 10.8 - 5.4
    else:
        body_fat = 1.20 * bmi + 0.23 * age - 5.4

    BODY_FAT_OFFSET = 1.5
    body_fat += BODY_FAT_OFFSET
    body_fat = max(5, min(body_fat, 45))

    fat_mass = weight * body_fat / 100
    lean_mass = weight - fat_mass

    EUFY_MUSCLE_FACTOR = 0.95
    muscle = lean_mass * EUFY_MUSCLE_FACTOR
    water = lean_mass * 0.73

    return body_fat, water, muscle


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
    if len(data) < 8 or data[0] != 0xCF or data[1] == 0x00:
        return None
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
        if self._status in ("scanning", "connected"):
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

        while not self._stop_event.is_set():
            try:
                device = await self._find_device()
                if device is None:
                    logger.warning("Scale '%s' not found. Retrying in 5s...", TARGET_NAME)
                    await asyncio.sleep(5)
                    continue

                self._set_status("connected")
                logger.info("Connecting to %s (%s)...", device.name, device.address)

                async with BleakClient(device) as client:
                    await client.start_notify(NOTIFY_UUID, self._on_notification)
                    logger.info("Listening for scale data...")

                    while not self._stop_event.is_set():
                        if not client.is_connected:
                            logger.warning("Scale disconnected unexpectedly.")
                            break
                        await asyncio.sleep(0.5)

            except Exception:
                logger.exception("BLE error — will retry in 5s.")
                self._set_status("scanning")
                await asyncio.sleep(5)

        self._set_status("idle")

    async def _find_device(self):
        devices = await BleakScanner.discover(timeout=8.0)
        for d in devices:
            if d.name and TARGET_NAME in d.name:
                return d
        return None

    def _on_notification(self, sender, data: bytearray):
        result = decode_packet(bytes(data))

        if result == "finished":
            logger.info("Scale measurement finished.")
            self._set_status("finished")
            if self._latest:
                self._socketio.emit("bluetooth:finished", self._latest)
            return

        if result is None:
            return

        weight, impedance = result
        p = self._session_params

        fat_pct, water_kg, muscle_kg = body_composition(
            weight=weight,
            impedance=impedance,
            height_cm=p.get("height_cm") or 170,
            age=p.get("age") or 30,
            is_male=p.get("is_male", True),
        )

        fat_mass = round(weight * fat_pct / 100, 2) if fat_pct else None

        self._latest = {
            "patient_id": p.get("patient_id"),
            "weight": round(weight, 2),
            "impedance": round(impedance, 1),
            "body_fat_pct": round(fat_pct, 1) if fat_pct else None,
            "fat_mass": fat_mass,
            "muscle_mass": round(muscle_kg, 2) if muscle_kg else None,
            "water_kg": round(water_kg, 2) if water_kg else None,
        }

        self._socketio.emit("bluetooth:data", self._latest)
        logger.info("BLE data: weight=%.2f kg, body_fat=%.1f%%", weight, fat_pct or 0)
