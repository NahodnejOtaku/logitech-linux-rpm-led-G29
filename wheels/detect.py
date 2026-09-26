from wheels.wheels import G27
from wheels.wheels import G29
from wheels.wheels import G923xbox
from wheels.wheels import G923ps
from wheels.wheels import GPROxbox
from wheels.wheels import GPROps4
from wheels.wheels import RS50
from wheels.base import BaseWheel
from wheels.hid_backend import enumerate_devices
from wheels.sysfs_backend import find_g29_leds

# Register every VID/PID with its class
DEVICE_MAP: dict[tuple[int, int], type[BaseWheel]] = {}
for cls in (G27, G29, G923xbox, G923ps, GPROxbox, GPROps4, RS50):
    for pid in cls.PRODUCT_IDS:
        DEVICE_MAP[(cls.VENDOR_ID, pid)] = cls


WheelFailure = tuple[str, int, Exception | None]

PERMISSION_HINT = ("Check that no other application is using the wheel and that you have "
                   "hidraw permissions (see the udev rule in the README).")


def find_wheel_with_failures() -> tuple[BaseWheel | None, list[WheelFailure]]:
    """Return a connected wheel plus the wheels that were seen but unusable.

    The failures matter to the UI: "nothing plugged in" and "plugged in but no
    permission" need different advice, and only the caller can display it.
    """
    failures: list[WheelFailure] = []

    # G29: prefer the Linux LED class interface. This allows the RPM LEDs
    # to be controlled without opening the HID interface of the wheel.
    g29_leds, g29_product = find_g29_leds()
    if g29_leds:
        wheel = G29()
        product_id = int(g29_product, 16) if g29_product else None

        if wheel.connect(product_id):
            print(f"✔  G29 detected ({hex(product_id) if product_id else 'sysfs'})")
            return wheel, []

        failures.append((
            "G29",
            product_id or 0,
            wheel.last_error
        ))

        # Do NOT fall back to HID for a G29 whose sysfs interface exists.
        # Otherwise, this application could still claim the wheel.
        for name, failed_product_id, error in failures:
            print(
                f"✖  {name} ({hex(failed_product_id)}) "
                f"was found but could not be opened: {error}"
            )

        return None, failures

    for dev in enumerate_devices():
        cls = DEVICE_MAP.get((dev['vendor_id'], dev['product_id']))
        if not cls:
            continue
        wheel = cls()
        if wheel.connect(dev['product_id']):
            print(f"✔  {cls.__name__} detected "
                  f"({hex(dev['product_id'])})")
            return wheel, []
        failures.append((cls.__name__, dev['product_id'], wheel.last_error))

    for name, product_id, error in failures:
        print(f"✖  {name} ({hex(product_id)}) was found but could not be opened: {error}")
    if failures:
        print("   " + PERMISSION_HINT)
    return None, failures


def find_wheel() -> BaseWheel | None:
    """Return a connected wheel instance or None."""
    wheel, _failures = find_wheel_with_failures()
    return wheel
