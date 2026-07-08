"""
Bluetooth background service for the Eufy C1 Smart Scale (T9146).

The public API and Socket.IO events are intentionally kept compatible with
the previous service:

Public methods:
    get_status()
    get_latest_measurement()
    start_scan()
    stop_scan()

Socket.IO events:
    bluetooth:status
    bluetooth:data
    bluetooth:finished
"""

import asyncio
import logging
import threading
import time
from datetime import datetime

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakCharacteristicNotFoundError


logger = logging.getLogger(__name__)


TARGET_NAME = "T9146"

SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000fff4-0000-1000-8000-00805f9b34fb"

DISCOVERY_TIMEOUT_SECONDS = 30.0
RETRY_DELAY_SECONDS = 2.0
POST_COMPLETION_GRACE_SECONDS = 1.0

STABLE_PACKET_CONFIRMATIONS = 2
IMPEDANCE_PACKET_CONFIRMATIONS = 2

MIN_WEIGHT_KG = 20.0
MAX_WEIGHT_KG = 250.0
MIN_IMPEDANCE_OHMS = 100.0
MAX_IMPEDANCE_OHMS = 1500.0


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
    Return calculated body metrics, or None when impedance is invalid.

    The formulas are retained from the previous service so callers receive
    the same measurement fields as before.
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
        met_age = (
            -1.1165 * height_cm
            + 1.5784 * weight
            + 0.4615 * age
            + 0.0415 * impedance
            + 83.2548
        )
    else:
        met_age = (
            -0.7471 * height_cm
            + 0.9161 * weight
            + 0.4184 * age
            + 0.0517 * impedance
            + 54.2267
        )
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


def xor_checksum(data: bytes) -> int:
    """Return XOR checksum of all bytes."""
    value = 0
    for byte in data:
        value ^= byte
    return value


def build_initialization_packet() -> bytes:
    """Build the 11-byte FD initialization frame."""
    payload = bytes.fromhex("FD 00 00 00 00 00 00 00 00 00")
    return payload + bytes([xor_checksum(payload)])


def build_time_packet(now: datetime | None = None) -> bytes:
    """Build the F1 date/time synchronization command."""
    now = now or datetime.now()
    return bytes(
        [
            0xF1,
            (now.year >> 8) & 0xFF,
            now.year & 0xFF,
            now.month,
            now.day,
            now.hour,
            now.minute,
            now.second,
        ]
    )


def valid_checksum(packet: bytes) -> bool:
    """Validate the XOR checksum used by 11-byte live CF packets."""
    return len(packet) == 11 and xor_checksum(packet[:-1]) == packet[-1]


def decode_impedance(data):
    """
    Decode impedance from bytes 1-2 of a CF packet.

    The value is little-endian and expressed in tenths of an ohm.
    """
    if len(data) < 3 or data[0] != 0xCF:
        return None

    impedance_raw = int.from_bytes(data[1:3], byteorder="little", signed=False)
    if impedance_raw <= 0:
        return None

    return impedance_raw / 10.0


def decode_packet(data):
    """
    Compatibility decoder retained for the rest of the project.

    Returns:
        "finished" for F3 00
        (weight_kg, impedance_ohms) for a valid live impedance packet
        None for acknowledgements, history records, changing/stable weight
        packets, malformed packets, and invalid checksums
    """
    raw = bytes(data)

    if raw == b"\xf3\x00":
        return "finished"

    if len(raw) != 11 or raw[0] != 0xCF:
        return None

    if not valid_checksum(raw):
        return None

    weight_raw = int.from_bytes(raw[3:5], byteorder="little", signed=False)
    weight = weight_raw / 100.0

    if weight < MIN_WEIGHT_KG or weight > MAX_WEIGHT_KG:
        return None

    impedance = decode_impedance(raw)
    if impedance is None:
        return None

    if impedance < MIN_IMPEDANCE_OHMS or impedance > MAX_IMPEDANCE_OHMS:
        return None

    return weight, impedance


# --- BluetoothService wraps async bleak in a background thread ---

class BluetoothService:
    def __init__(self, socketio):
        self._socketio = socketio
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._state_lock = threading.RLock()

        self._status = "idle"  # idle | scanning | connected | finished | error
        self._latest: dict | None = None
        self._session_params: dict = {}

        # Diagnostics / session tracking
        self._measurement_id = 0
        self._connection_id = 0
        self._packet_count = 0
        self._finished_emitted = False
        self._last_notification_time: float | None = None

        # Physical measurement state
        self._weight_activity_seen = False
        self._stable_weight_seen = False
        self._last_stable_weight_raw: int | None = None
        self._stable_packet_count = 0
        self._stable_weight_kg: float | None = None

        self._last_impedance_key: tuple[int, int] | None = None
        self._impedance_packet_count = 0
        self._impedance_confirmed = False
        self._f300_seen = False
        self._session_ended_incomplete = False

        # Async events are created inside the BLE event-loop thread
        self._time_ack_event: asyncio.Event | None = None
        self._history_ack_event: asyncio.Event | None = None
        self._live_ack_event: asyncio.Event | None = None
        self._measurement_complete_event: asyncio.Event | None = None

        logger.info("BluetoothService initialized.")

    # --- Public API (called from Flask routes, runs in Flask thread) ---

    def get_status(self) -> dict:
        with self._state_lock:
            latest = self._latest.copy() if self._latest else None
            return {"status": self._status, "latest": latest}

    def get_latest_measurement(self) -> dict | None:
        with self._state_lock:
            return self._latest.copy() if self._latest else None

    def start_scan(self, patient_id=None, height_cm=None, age=None, is_male=True):
        logger.info(
            "START_SCAN requested patient=%s height=%s age=%s is_male=%s",
            patient_id,
            height_cm,
            age,
            is_male,
        )

        if self._thread and self._thread.is_alive():
            # A completed worker may still be inside the short disconnect grace
            # period. Ask it to stop and join instead of rejecting the new patient.
            if self._status == "finished":
                logger.info("Previous measurement finished; closing its BLE worker.")
                self._stop_event.set()
                self._wake_async_waiters()
                self._thread.join(timeout=5.0)
            elif not self._stop_event.is_set():
                logger.warning(
                    "Scan already running for session=%d; ignoring start_scan().",
                    self._measurement_id,
                )
                return
            else:
                logger.info("Waiting for previous scan thread to exit...")
                self._thread.join(timeout=8.0)

            if self._thread.is_alive():
                logger.error(
                    "Previous scan thread did not stop in time; cannot start a new session."
                )
                return

        with self._state_lock:
            self._measurement_id += 1
            self._packet_count = 0
            self._finished_emitted = False
            self._last_notification_time = None

            self._session_params = {
                "patient_id": patient_id,
                "height_cm": height_cm,
                "age": age,
                "is_male": is_male,
            }

            # This is the critical stale-patient guard.
            self._latest = None
            self._reset_physical_measurement_state(clear_latest=False)

            current_measurement_id = self._measurement_id

        self._stop_event.clear()
        self._set_status("scanning")

        logger.info(
            "NEW MEASUREMENT SESSION id=%d params=%s",
            current_measurement_id,
            self._session_params,
        )

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"BLE-Scale-{current_measurement_id}",
            daemon=True,
        )
        self._thread.start()

    def stop_scan(self):
        logger.info(
            "Bluetooth scan stopped by user session=%d status=%s",
            self._measurement_id,
            self._status,
        )
        self._stop_event.set()
        self._wake_async_waiters()
        self._set_status("idle")

    # --- Internal helpers ---

    def _set_status(self, status: str):
        with self._state_lock:
            old_status = self._status
            self._status = status
            measurement_id = self._measurement_id

        logger.info(
            "Bluetooth status %s -> %s session=%d",
            old_status,
            status,
            measurement_id,
        )
        self._socketio.emit("bluetooth:status", {"status": status})

    def _wake_async_waiters(self):
        loop = self._loop
        if loop is None or loop.is_closed():
            return

        def _wake():
            if self._measurement_complete_event is not None:
                self._measurement_complete_event.set()

        try:
            loop.call_soon_threadsafe(_wake)
        except RuntimeError:
            # The loop may have closed between the checks above.
            pass

    def _reset_physical_measurement_state(self, clear_latest: bool):
        """
        Reset only physical packet state.

        Protocol acknowledgements are connection-scoped and are initialized
        separately after each connection.
        """
        self._weight_activity_seen = False
        self._stable_weight_seen = False
        self._last_stable_weight_raw = None
        self._stable_packet_count = 0
        self._stable_weight_kg = None

        self._last_impedance_key = None
        self._impedance_packet_count = 0
        self._impedance_confirmed = False
        self._f300_seen = False
        self._session_ended_incomplete = False
        self._last_notification_time = None

        if clear_latest:
            self._latest = None

    def _run_loop(self):
        if self._loop is None:
            logger.error("BLE event loop was not created.")
            self._set_status("error")
            return

        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._scan_and_connect())
        except asyncio.CancelledError:
            # asyncio.CancelledError inherits from BaseException, so a normal
            # ``except Exception`` block does not catch it.  A cancellation is
            # expected during an explicit stop, but otherwise it must be logged
            # without allowing an unhandled traceback to escape the worker.
            if self._stop_event.is_set():
                logger.info(
                    "BLE event loop cancelled during requested shutdown session=%d.",
                    self._measurement_id,
                )
            else:
                logger.exception(
                    "BLE event loop was cancelled unexpectedly session=%d.",
                    self._measurement_id,
                )
                self._set_status("error")
        except Exception:
            logger.exception(
                "Fatal error in Bluetooth event loop session=%d.",
                self._measurement_id,
            )
            if not self._stop_event.is_set():
                self._set_status("error")
        finally:
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception:
                logger.exception("Error while cancelling BLE tasks.")
            finally:
                self._loop.close()

            logger.info(
                "BLE worker exited session=%d final_status=%s",
                self._measurement_id,
                self._status,
            )

    async def _scan_and_connect(self):
        logger.info(
            "Starting event-driven BLE scan for '%s' session=%d.",
            TARGET_NAME,
            self._measurement_id,
        )

        known_address = None

        while not self._stop_event.is_set() and self._status != "finished":
            try:
                if known_address is None:
                    device = await self._find_device()

                    if self._stop_event.is_set():
                        break

                    if device is None:
                        logger.warning(
                            "Scale '%s' not found during %.1fs discovery window; "
                            "retrying in %.1fs.",
                            TARGET_NAME,
                            DISCOVERY_TIMEOUT_SECONDS,
                            RETRY_DELAY_SECONDS,
                        )
                        await self._sleep_interruptibly(RETRY_DELAY_SECONDS)
                        continue

                    known_address = device.address
                    target = device

                    logger.info(
                        "Scale found name=%s address=%s session=%d.",
                        device.name,
                        device.address,
                        self._measurement_id,
                    )
                else:
                    target = known_address

                services_changed = False

                def _on_services_changed(_):
                    nonlocal services_changed
                    services_changed = True
                    logger.warning(
                        "GATT services changed address=%s session=%d.",
                        known_address,
                        self._measurement_id,
                    )

                logger.info(
                    "Connecting to scale address=%s session=%d.",
                    known_address,
                    self._measurement_id,
                )

                async with BleakClient(
                    target,
                    timeout=40.0,
                    services_changed_callback=_on_services_changed,
                ) as client:
                    self._connection_id += 1
                    connection_id = self._connection_id

                    self._time_ack_event = asyncio.Event()
                    self._history_ack_event = asyncio.Event()
                    self._live_ack_event = asyncio.Event()
                    self._measurement_complete_event = asyncio.Event()

                    self._set_status("connected")
                    logger.info(
                        "BLE connected address=%s session=%d connection=%d.",
                        known_address,
                        self._measurement_id,
                        connection_id,
                    )

                    await asyncio.sleep(0.25)
                    await self._start_notifications(client)

                    # Parsing starts immediately after notification subscription.
                    # Initialization runs afterwards and never resets physical
                    # measurement state.
                    initialization_task = asyncio.create_task(
                        self._initialize_scale(client),
                        name=f"scale-init-{self._measurement_id}-{connection_id}",
                    )

                    logger.info(
                        "Listening for live scale data session=%d connection=%d.",
                        self._measurement_id,
                        connection_id,
                    )

                    while not self._stop_event.is_set():
                        if self._measurement_complete_event.is_set():
                            logger.info(
                                "Confirmed impedance result; keeping connection alive "
                                "for %.1fs final-packet grace period.",
                                POST_COMPLETION_GRACE_SECONDS,
                            )
                            await asyncio.sleep(POST_COMPLETION_GRACE_SECONDS)
                            break

                        if not client.is_connected:
                            logger.warning(
                                "Scale disconnected session=%d connection=%d "
                                "impedance_confirmed=%s f300_seen=%s.",
                                self._measurement_id,
                                connection_id,
                                self._impedance_confirmed,
                                self._f300_seen,
                            )
                            break

                        await asyncio.sleep(0.2)

                    if not initialization_task.done():
                        initialization_task.cancel()
                    await asyncio.gather(initialization_task, return_exceptions=True)

                    if client.is_connected:
                        try:
                            await client.stop_notify(NOTIFY_UUID)
                            logger.info(
                                "BLE notifications stopped session=%d connection=%d.",
                                self._measurement_id,
                                connection_id,
                            )
                        except Exception:
                            logger.debug(
                                "Unable to stop notifications cleanly.",
                                exc_info=True,
                            )

                if self._status == "finished":
                    logger.info(
                        "Measurement session=%d completed; BLE worker will stop.",
                        self._measurement_id,
                    )
                    break

                if self._stop_event.is_set():
                    break

                if services_changed:
                    logger.info(
                        "Reconnecting immediately after GATT service change "
                        "session=%d.",
                        self._measurement_id,
                    )
                    self._set_status("scanning")
                    continue

                # If F3 00 arrived without confirmed impedance, or the scale
                # disconnected before completion, this physical attempt is
                # incomplete. Clear its partial values before the next wake-up.
                if self._session_ended_incomplete or not self._impedance_confirmed:
                    logger.warning(
                        "Incomplete scale attempt session=%d: "
                        "stable=%s impedance_packets=%d f300=%s. "
                        "Clearing partial data and waiting for the scale to wake again.",
                        self._measurement_id,
                        self._stable_weight_seen,
                        self._impedance_packet_count,
                        self._f300_seen,
                    )
                    with self._state_lock:
                        self._reset_physical_measurement_state(clear_latest=True)

                known_address = None
                self._set_status("scanning")

            except asyncio.CancelledError:
                # Bleak's WinRT backend can surface CancelledError while Windows
                # is enumerating GATT services.  That is a transient connection
                # failure when the task itself was not explicitly cancelled.
                current_task = asyncio.current_task()
                task_cancel_requested = bool(
                    current_task is not None and current_task.cancelling()
                )

                if self._stop_event.is_set() or task_cancel_requested:
                    logger.info(
                        "BLE operation cancelled during shutdown session=%d.",
                        self._measurement_id,
                    )
                    raise

                logger.warning(
                    "Windows cancelled BLE GATT discovery/connection "
                    "session=%d address=%s; treating it as transient and retrying.",
                    self._measurement_id,
                    known_address,
                )

                known_address = None
                with self._state_lock:
                    if not self._impedance_confirmed:
                        self._reset_physical_measurement_state(clear_latest=True)
                self._set_status("scanning")
                await self._sleep_interruptibly(RETRY_DELAY_SECONDS)

            except Exception:
                logger.exception(
                    "BLE error session=%d; clearing connection and retrying.",
                    self._measurement_id,
                )

                if self._stop_event.is_set():
                    break

                known_address = None
                with self._state_lock:
                    if not self._impedance_confirmed:
                        self._reset_physical_measurement_state(clear_latest=True)
                self._set_status("scanning")
                await self._sleep_interruptibly(RETRY_DELAY_SECONDS)

        if self._thread is threading.current_thread() and self._status != "finished":
            self._set_status("idle")

    async def _start_notifications(self, client: BleakClient):
        for attempt in range(1, 4):
            try:
                await client.start_notify(NOTIFY_UUID, self._on_notification)
                logger.info(
                    "BLE notification enabled uuid=%s attempt=%d session=%d.",
                    NOTIFY_UUID,
                    attempt,
                    self._measurement_id,
                )
                return
            except BleakCharacteristicNotFoundError:
                if attempt == 3:
                    raise

                logger.warning(
                    "Notification characteristic not ready attempt=%d/3; "
                    "retrying in 1s.",
                    attempt,
                )
                await asyncio.sleep(1.0)

    async def _initialize_scale(self, client: BleakClient):
        """
        Execute the validated command sequence:

            FD initialization
            F1 current date/time
            F2 00 history request
            F2 01 live-mode request

        Live CF packets are parsed concurrently and are never gated on these
        acknowledgements.
        """
        try:
            await self._write_command(
                client,
                build_initialization_packet(),
                "FD initialization",
            )
            await asyncio.sleep(0.1)

            if self._time_ack_event is not None:
                self._time_ack_event.clear()
            await self._write_command(
                client,
                build_time_packet(),
                "F1 time synchronization",
            )
            await self._wait_for_ack(
                self._time_ack_event,
                "F1 00 time acknowledgement",
                timeout=2.0,
            )

            if self._history_ack_event is not None:
                self._history_ack_event.clear()
            await self._write_command(client, b"\xf2\x00", "F2 00 history request")
            await self._wait_for_ack(
                self._history_ack_event,
                "F2 00 history completion",
                timeout=3.0,
            )

            if self._live_ack_event is not None:
                self._live_ack_event.clear()
            await self._write_command(client, b"\xf2\x01", "F2 01 live mode")
            await self._wait_for_ack(
                self._live_ack_event,
                "F2 01 live-mode acknowledgement",
                timeout=2.0,
            )

            logger.info(
                "Scale initialization sequence completed session=%d.",
                self._measurement_id,
            )

        except asyncio.CancelledError:
            raise
        except Exception:
            # Do not stop live parsing because successful measurements can begin
            # before, during, or even without all acknowledgements.
            logger.exception(
                "Scale initialization sequence had an error; "
                "continuing to listen for live packets session=%d.",
                self._measurement_id,
            )

    async def _write_command(
        self,
        client: BleakClient,
        payload: bytes,
        description: str,
    ):
        logger.info(
            "BLE WRITE session=%d command=%s data=%s.",
            self._measurement_id,
            description,
            payload.hex(),
        )

        for attempt in range(1, 4):
            try:
                await client.write_gatt_char(WRITE_UUID, payload, response=True)
                return
            except BleakCharacteristicNotFoundError:
                if attempt == 3:
                    raise

                logger.warning(
                    "Write characteristic not ready command=%s attempt=%d/3; "
                    "retrying in 0.5s.",
                    description,
                    attempt,
                )
                await asyncio.sleep(0.5)

    async def _wait_for_ack(
        self,
        event: asyncio.Event | None,
        description: str,
        timeout: float,
    ):
        if event is None:
            logger.warning("Cannot wait for %s: event is unavailable.", description)
            return

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            logger.info(
                "BLE ACK received session=%d acknowledgement=%s.",
                self._measurement_id,
                description,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "BLE ACK timeout session=%d acknowledgement=%s timeout=%.1fs; "
                "continuing.",
                self._measurement_id,
                description,
                timeout,
            )

    async def _sleep_interruptibly(self, seconds: float):
        deadline = asyncio.get_running_loop().time() + seconds
        while not self._stop_event.is_set():
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return
            await asyncio.sleep(min(0.2, remaining))

    async def _find_device(self):
        """
        Event-driven discovery.

        Unlike BleakScanner.discover(timeout=...), this returns immediately when
        the target advertisement is seen instead of waiting for the full timeout.
        """
        loop = asyncio.get_running_loop()
        found_event = asyncio.Event()
        found_device = {"device": None}

        def _detection_callback(device, advertisement_data):
            name = device.name or getattr(advertisement_data, "local_name", None) or ""
            logger.debug(
                "BLE advertisement name=%s address=%s rssi=%s.",
                name,
                device.address,
                getattr(advertisement_data, "rssi", None),
            )

            if found_device["device"] is None and TARGET_NAME.lower() in name.lower():
                found_device["device"] = device
                loop.call_soon_threadsafe(found_event.set)

        scanner = BleakScanner(detection_callback=_detection_callback)

        logger.info(
            "BLE discovery started event-driven timeout=%.1fs session=%d.",
            DISCOVERY_TIMEOUT_SECONDS,
            self._measurement_id,
        )

        await scanner.start()

        try:
            deadline = loop.time() + DISCOVERY_TIMEOUT_SECONDS

            while not self._stop_event.is_set():
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break

                try:
                    await asyncio.wait_for(
                        found_event.wait(),
                        timeout=min(0.25, remaining),
                    )
                except asyncio.TimeoutError:
                    continue

                device = found_device["device"]
                if device is not None:
                    logger.info(
                        "TARGET SCALE FOUND name=%s address=%s; "
                        "stopping discovery immediately.",
                        device.name,
                        device.address,
                    )
                    return device

            return None
        finally:
            try:
                await scanner.stop()
            except asyncio.CancelledError:
                current_task = asyncio.current_task()
                if (
                    self._stop_event.is_set()
                    or (current_task is not None and current_task.cancelling())
                ):
                    raise
                logger.warning(
                    "Windows cancelled BLE scanner shutdown; continuing.",
                    exc_info=True,
                )
            except Exception:
                logger.debug("BLE scanner stop failed.", exc_info=True)

            logger.info(
                "BLE discovery stopped session=%d target_found=%s.",
                self._measurement_id,
                found_device["device"] is not None,
            )

    def _on_notification(self, sender, data: bytearray):
        if self._stop_event.is_set():
            logger.debug("Ignoring BLE notification because stop_scan() was requested.")
            return

        raw = bytes(data)
        now = time.monotonic()

        with self._state_lock:
            self._packet_count += 1
            packet_number = self._packet_count
            previous_time = self._last_notification_time
            self._last_notification_time = now

        delta_ms = None if previous_time is None else (now - previous_time) * 1000.0

        logger.info(
            "BLE PACKET session=%d count=%d sender=%s length=%d "
            "delta_ms=%s raw=%s.",
            self._measurement_id,
            packet_number,
            sender,
            len(raw),
            "first" if delta_ms is None else f"{delta_ms:.0f}",
            raw.hex(),
        )

        # --- Two-byte protocol acknowledgements / markers ---

        if raw == b"\xf1\x00":
            logger.info("Received F1 00 time acknowledgement.")
            if self._time_ack_event is not None:
                self._time_ack_event.set()
            return

        if raw == b"\xf2\x00":
            logger.info("Received F2 00 history completion acknowledgement.")
            if self._history_ack_event is not None:
                self._history_ack_event.set()
            return

        if raw == b"\xf2\x01":
            logger.info("Received F2 01 live-mode acknowledgement.")
            if self._live_ack_event is not None:
                self._live_ack_event.set()
            return

        if raw == b"\xf5\x00":
            logger.info(
                "Received optional F5 00 awake/session marker; "
                "physical measurement state is unchanged."
            )
            return

        if raw == b"\xf3\x00":
            self._f300_seen = True

            if self._impedance_confirmed:
                logger.info(
                    "Received F3 00 after confirmed impedance session=%d; "
                    "normal scale shutdown marker.",
                    self._measurement_id,
                )
            else:
                self._session_ended_incomplete = True
                logger.warning(
                    "Received F3 00 before confirmed impedance session=%d "
                    "stable=%s impedance_packets=%d. "
                    "The attempt is incomplete; no finished event will be emitted.",
                    self._measurement_id,
                    self._stable_weight_seen,
                    self._impedance_packet_count,
                )
            return

        # --- Stored historical records ---

        if len(raw) == 18 and raw[0] == 0xCF:
            history = self._decode_history_packet(raw)
            if history is None:
                logger.warning("Ignored malformed 18-byte history packet raw=%s.", raw.hex())
            else:
                logger.info("HISTORICAL SCALE RECORD %s.", history)
            return

        # --- Live measurement packets ---

        if len(raw) != 11 or raw[0] != 0xCF:
            logger.debug(
                "Ignored unknown BLE packet session=%d length=%d raw=%s.",
                self._measurement_id,
                len(raw),
                raw.hex(),
            )
            return

        if not valid_checksum(raw):
            logger.warning(
                "Ignored live packet with invalid XOR checksum session=%d raw=%s.",
                self._measurement_id,
                raw.hex(),
            )
            return

        impedance_raw = int.from_bytes(raw[1:3], byteorder="little", signed=False)
        weight_raw = int.from_bytes(raw[3:5], byteorder="little", signed=False)
        weight_kg = weight_raw / 100.0
        status = raw[9]

        if weight_raw <= 0 or not (MIN_WEIGHT_KG <= weight_kg <= MAX_WEIGHT_KG):
            logger.debug(
                "Ignored live packet with invalid weight raw=%d kg=%.2f status=%02x.",
                weight_raw,
                weight_kg,
                status,
            )
            return

        self._weight_activity_seen = True

        # Stable-weight packets carry zero impedance and status 01.
        if impedance_raw == 0:
            self._handle_weight_packet(
                raw=raw,
                weight_raw=weight_raw,
                weight_kg=weight_kg,
                status=status,
            )
            return

        impedance_ohms = impedance_raw / 10.0
        if not (MIN_IMPEDANCE_OHMS <= impedance_ohms <= MAX_IMPEDANCE_OHMS):
            logger.warning(
                "Ignored live packet with implausible impedance "
                "raw=%d ohms=%.1f weight=%.2f raw_packet=%s.",
                impedance_raw,
                impedance_ohms,
                weight_kg,
                raw.hex(),
            )
            return

        self._handle_impedance_packet(
            raw=raw,
            weight_raw=weight_raw,
            weight_kg=weight_kg,
            impedance_raw=impedance_raw,
            impedance_ohms=impedance_ohms,
            status=status,
        )

    def _handle_weight_packet(
        self,
        raw: bytes,
        weight_raw: int,
        weight_kg: float,
        status: int,
    ):
        if status != 0x01:
            # A changing-weight packet invalidates the consecutive stable count.
            self._last_stable_weight_raw = None
            self._stable_packet_count = 0
            logger.info(
                "WEIGHT CHANGING session=%d weight=%.2fkg status=%02x raw=%s.",
                self._measurement_id,
                weight_kg,
                status,
                raw.hex(),
            )
            return

        if self._last_stable_weight_raw == weight_raw:
            self._stable_packet_count += 1
        else:
            self._last_stable_weight_raw = weight_raw
            self._stable_packet_count = 1

        logger.info(
            "STABLE WEIGHT CANDIDATE session=%d weight=%.2fkg confirmation=%d/%d.",
            self._measurement_id,
            weight_kg,
            self._stable_packet_count,
            STABLE_PACKET_CONFIRMATIONS,
        )

        if (
            self._stable_packet_count >= STABLE_PACKET_CONFIRMATIONS
            and not self._stable_weight_seen
        ):
            self._stable_weight_seen = True
            self._stable_weight_kg = weight_kg
            logger.info(
                "STABLE WEIGHT CONFIRMED session=%d weight=%.2fkg. "
                "Waiting for impedance; the user must remain on the electrodes.",
                self._measurement_id,
                weight_kg,
            )

    def _handle_impedance_packet(
        self,
        raw: bytes,
        weight_raw: int,
        weight_kg: float,
        impedance_raw: int,
        impedance_ohms: float,
        status: int,
    ):
        key = (weight_raw, impedance_raw)

        if self._last_impedance_key == key:
            self._impedance_packet_count += 1
        else:
            self._last_impedance_key = key
            self._impedance_packet_count = 1

        if not self._stable_weight_seen:
            logger.warning(
                "IMPEDANCE packet arrived before two stable-weight packets were "
                "observed. Accepting it because connection may have started late."
            )

        latest = self._build_measurement(weight_kg, impedance_ohms)

        with self._state_lock:
            self._latest = latest

        logger.info(
            "IMPEDANCE CANDIDATE session=%d weight=%.2fkg impedance=%.1fohm "
            "status=%02x confirmation=%d/%d raw=%s.",
            self._measurement_id,
            weight_kg,
            impedance_ohms,
            status,
            self._impedance_packet_count,
            IMPEDANCE_PACKET_CONFIRMATIONS,
            raw.hex(),
        )

        # Preserve the existing event name and payload shape.
        self._socketio.emit("bluetooth:data", latest)

        if (
            self._impedance_packet_count >= IMPEDANCE_PACKET_CONFIRMATIONS
            and not self._impedance_confirmed
        ):
            self._impedance_confirmed = True
            logger.info(
                "IMPEDANCE CONFIRMED session=%d weight=%.2fkg impedance=%.1fohm.",
                self._measurement_id,
                weight_kg,
                impedance_ohms,
            )
            self._complete_measurement(latest)

    def _build_measurement(self, weight: float, impedance: float) -> dict:
        p = self._session_params

        metrics = body_composition(
            weight=weight,
            impedance=impedance,
            height_cm=p.get("height_cm") or 170,
            age=p.get("age") or 30,
            is_male=p.get("is_male", True),
        )

        return {
            "patient_id": p.get("patient_id"),
            "weight": round(weight, 2),
            "impedance": round(impedance, 1),
            **(metrics or {}),
        }

    def _complete_measurement(self, measurement: dict):
        with self._state_lock:
            if self._finished_emitted:
                return

            self._finished_emitted = True
            self._latest = measurement.copy()
            finished_data = self._latest.copy()

        logger.info(
            "FINAL MEASUREMENT CONFIRMED session=%d result=%s.",
            self._measurement_id,
            finished_data,
        )

        self._set_status("finished")
        self._socketio.emit("bluetooth:finished", finished_data)

        if self._measurement_complete_event is not None:
            self._measurement_complete_event.set()

    @staticmethod
    def _decode_history_packet(raw: bytes) -> dict | None:
        if len(raw) != 18 or raw[0] != 0xCF:
            return None

        impedance_raw = int.from_bytes(raw[1:3], byteorder="little", signed=False)
        weight_raw = int.from_bytes(raw[3:5], byteorder="little", signed=False)
        year = int.from_bytes(raw[11:13], byteorder="big", signed=False)

        try:
            timestamp = datetime(
                year,
                raw[13],
                raw[14],
                raw[15],
                raw[16],
                raw[17],
            )
        except ValueError:
            timestamp = None

        return {
            "weight": round(weight_raw / 100.0, 2),
            "impedance": round(impedance_raw / 10.0, 1),
            "timestamp": timestamp.isoformat(sep=" ") if timestamp else None,
            "raw": raw.hex(),
        }
