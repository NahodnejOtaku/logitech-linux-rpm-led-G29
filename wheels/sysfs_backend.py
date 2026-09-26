from __future__ import annotations

from pathlib import Path

from wheels.base import BaseWheel


LED_ROOT = Path("/sys/class/leds")
G29_PRODUCT_IDS = {"c24f", "c260"}


def find_g29_leds() -> tuple[dict[int, Path], str | None]:
    """
    Find the five RPM LED class devices belonging to a G29.

    Returns:
        ({1: RPM1 path, ..., 5: RPM5 path}, product_id)
        or ({}, None) if no G29 LED device is present.
    """
    leds: dict[int, Path] = {}

    for index in range(1, 6):
        matches = list(LED_ROOT.glob(f"*::RPM{index}"))

        for led in matches:
            resolved = led.resolve()

            for parent in (resolved, *resolved.parents):
                vendor_path = parent / "idVendor"
                product_path = parent / "idProduct"

                if not vendor_path.is_file() or not product_path.is_file():
                    continue

                try:
                    vendor = vendor_path.read_text().strip().lower()
                    product = product_path.read_text().strip().lower()
                except OSError:
                    continue

                if vendor == "046d" and product in G29_PRODUCT_IDS:
                    leds[index] = led
                    break

            if index in leds:
                break

    if len(leds) != 5:
        return {}, None

    product_id = None

    # Determine the product ID from any of the matched LED paths.
    resolved = leds[1].resolve()
    for parent in (resolved, *resolved.parents):
        product_path = parent / "idProduct"
        if product_path.is_file():
            try:
                value = product_path.read_text().strip().lower()
            except OSError:
                continue

            if value in G29_PRODUCT_IDS:
                product_id = value
                break

    return leds, product_id


class SysfsG29(BaseWheel):
    """
    G29 RPM LED backend using the Linux LED class.

    Unlike HIDClassic, this class never opens /dev/hidraw and therefore
    does not claim the HID interface used by the steering wheel.
    """

    PRODUCT_IDS = (0xC24F, 0xC260)

    def __init__(self) -> None:
        super().__init__()
        self._leds: dict[int, Path] = {}

    def connect(self, product_id: int | None = None) -> bool:
        self.last_error = None

        leds, detected_product = find_g29_leds()

        if not leds:
            self.last_error = RuntimeError(
                "G29 RPM LED sysfs devices were not found"
            )
            return False

        if product_id is not None:
            expected = f"{product_id:04x}"
            if detected_product != expected:
                self.last_error = RuntimeError(
                    f"Found G29 LEDs for product {detected_product}, "
                    f"expected {expected}"
                )
                return False

        try:
            for led in leds.values():
                if not led.joinpath("brightness").is_file():
                    raise RuntimeError(
                        f"Missing brightness attribute: {led / 'brightness'}"
                    )

            # Do not change the LEDs here. Merely verify that the existing
            # udev permissions allow us to write them.
            for led in leds.values():
                with (led / "brightness").open("r+"):
                    pass

        except OSError as error:
            self.last_error = error
            return False

        self._leds = leds
        self._dev = object()  # Marker: connected without a HID handle.
        self._last_bits = -1
        return True

    def close(self) -> None:
        self._leds.clear()
        self._dev = None

    def leds_rpm(self, percent: float) -> None:
        if not self._leds:
            return

        bits = self._percent_to_bits(percent)

        if bits == self._last_bits:
            return

        self._last_bits = bits

        for index in range(1, 6):
            value = "1" if bits & (1 << (index - 1)) else "0"

            try:
                (self._leds[index] / "brightness").write_text(value)
            except OSError as error:
                self.last_error = error

    def _led_report(self, bits: int):
        # Not used by the sysfs implementation. BaseWheel requires this
        # method because the original wheel backends use HID reports.
        return ()