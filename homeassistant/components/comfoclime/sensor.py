"""Sensor platform for ComfoClime integration."""

import logging

import aiohttp

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the ComfoClime sensors from a config entry."""
    ip_address = entry.data.get("ip_address")

    # Fetch the system UUID.
    system_uuid = await fetch_system_uuid(ip_address)
    if not system_uuid:
        _LOGGER.error("Failed to fetch system UUID")
        return

    # Fetch the UUIDs of the devices.
    device_uuids = await fetch_device_uuids(ip_address, system_uuid)
    if not device_uuids:
        _LOGGER.error("Failed to fetch devices")
        return

    # Open a shared session.
    session = aiohttp.ClientSession()

    sensors = []

    # Add sensors for ComfoClime.
    if device_uuids.get("clime_uuid"):
        sensors.extend(
            [
                ComfoClimeSensor(
                    session,
                    ip_address,
                    system_uuid,
                    device_uuids["clime_uuid"],
                    "ComfoClime Indoor Temperature",
                    "indoorTemperature",
                    UnitOfTemperature.CELSIUS,
                ),
                ComfoClimeSensor(
                    session,
                    ip_address,
                    system_uuid,
                    device_uuids["clime_uuid"],
                    "ComfoClime Supply Temperature",
                    "supplyTemperature",
                    UnitOfTemperature.CELSIUS,
                ),
                ComfoClimeSensor(
                    session,
                    ip_address,
                    system_uuid,
                    device_uuids["clime_uuid"],
                    "ComfoClime Heat Pump Status",
                    "heatPumpStatus",
                    None,
                ),
            ]
        )

    # Add sensors for ventilation
    if device_uuids.get("ventilation_uuid"):
        sensors.extend(
            [
                ComfoClimeSensor(
                    session,
                    ip_address,
                    system_uuid,
                    device_uuids["ventilation_uuid"],
                    "Ventilation Outdoor Temperature",
                    "outdoorTemperature",
                    UnitOfTemperature.CELSIUS,
                ),
                ComfoClimeSensor(
                    session,
                    ip_address,
                    system_uuid,
                    device_uuids["ventilation_uuid"],
                    "Ventilation Extract Temperature",
                    "extractTemperature",
                    UnitOfTemperature.CELSIUS,
                ),
                ComfoClimeSensor(
                    session,
                    ip_address,
                    system_uuid,
                    device_uuids["ventilation_uuid"],
                    "Ventilation Exhaust Temperature",
                    "exhaustTemperature",
                    UnitOfTemperature.CELSIUS,
                ),
                ComfoClimeSensor(
                    session,
                    ip_address,
                    system_uuid,
                    device_uuids["ventilation_uuid"],
                    "Ventilation Supply Temperature",
                    "supplyTemperature",
                    UnitOfTemperature.CELSIUS,
                ),
                ComfoClimeSensor(
                    session,
                    ip_address,
                    system_uuid,
                    device_uuids["ventilation_uuid"],
                    "Ventilation Fan Speed",
                    "fanSpeed",
                    None,
                ),
            ]
        )

    async_add_entities(sensors, update_before_add=True)

    # Properly close the session when Home Assistant shuts down.
    hass.bus.async_listen_once("homeassistant_stop", lambda event: session.close())


async def fetch_system_uuid(ip_address):
    """Fetch the system UUID dynamically."""
    url = f"http://{ip_address}/system/systems"
    headers = {"Authorization": "Bearer null"}
    async with (
        aiohttp.ClientSession() as session,
        session.get(url, headers=headers) as response,
    ):
        if response.status != 200:
            return None
        data = await response.json()
        return data.get("systems", [])[0].get("uuid")


async def fetch_device_uuids(ip_address, system_uuid):
    """Fetch devices and return their UUIDs based on their names."""
    url = f"http://{ip_address}/system/{system_uuid}/devices"
    headers = {"Authorization": "Bearer null"}
    async with (
        aiohttp.ClientSession() as session,
        session.get(url, headers=headers) as response,
    ):
        if response.status != 200:
            return None

        data = await response.json()
        ventilation_uuid = None
        clime_uuid = None

        for device in data.get("devices", []):
            device_name = device.get("name", "").lower()
            if "comfoairq" in device_name:
                ventilation_uuid = device.get("uuid")
            elif "comfoclime" in device_name:
                clime_uuid = device.get("uuid")

        return {"ventilation_uuid": ventilation_uuid, "clime_uuid": clime_uuid}


class ComfoClimeSensor(SensorEntity):
    """Representation of a ComfoClime sensor."""

    def __init__(
        self, session, ip_address, system_uuid, device_uuid, name, attribute, unit
    ) -> None:
        """Initialize the ComfoClime sensor."""
        self._session = session
        self._ip_address = ip_address
        self._system_uuid = system_uuid
        self._device_uuid = device_uuid
        self._name = name
        self._attribute = attribute
        self._unit = unit
        self._state = None
        self._available = False

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name

    @property
    def native_value(self) -> str | int | float | None:
        """Return the state of the sensor."""
        return self._state

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement of the sensor."""
        return self._unit

    @property
    def available(self) -> bool:
        """Return True if the sensor is available."""
        return self._available

    async def async_update(self) -> None:
        """Fetch the latest data for the sensor."""
        url = f"http://{self._ip_address}/device/{self._device_uuid}/definition"
        headers = {"Authorization": "Bearer null"}
        try:
            async with self._session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    self._state = data.get(self._attribute)
                    self._available = True
                else:
                    self._available = False
        except aiohttp.ClientResponseError as e:
            _LOGGER.error("Client response error while fetching sensor data: %s", e)
            self._available = False
        except aiohttp.ClientConnectionError as e:
            _LOGGER.error("Client connection error while fetching sensor data: %s", e)
            self._available = False
        except aiohttp.ClientPayloadError as e:
            _LOGGER.error("Client payload error while fetching sensor data: %s", e)
            self._available = False
        except aiohttp.ClientError as e:
            _LOGGER.error("Connection error while fetching sensor data: %s", e)
            self._available = False
