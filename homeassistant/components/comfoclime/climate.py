"""ComfoClime climate integration for Home Assistant."""

import logging

import aiohttp

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up ComfoClime climate entity from a config entry."""
    ip_address = entry.data.get("ip_address")

    system_uuid = await fetch_system_uuid(ip_address)
    if not system_uuid:
        _LOGGER.error("Failed to fetch system UUID")
        return

    device_uuids = await fetch_device_uuids(ip_address, system_uuid)
    if not device_uuids:
        _LOGGER.error("Failed to fetch devices")
        return

    async_add_entities(
        [ComfoClimeClimate(hass, str(ip_address), system_uuid, device_uuids)],
        update_before_add=True,
    )


async def fetch_system_uuid(ip_address):
    """Fetch the system UUID from the given IP address."""
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
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(url, headers=headers) as response,
        ):
            if response.status != 200:
                _LOGGER.error(
                    "Failed to fetch devices. Status code: %s", response.status
                )
                return None

            data = await response.json()
            _LOGGER.debug("Fetched devices data: %s", data)

            # Initialize the UUIDs.
            ventilation_uuid = None
            clime_uuid = None

            # Search devices based on partial name.
            for device in data.get("devices", []):
                device_name = device.get("name", "").lower()
                _LOGGER.debug("Checking device: %s", device)

                # Search for the ventilation unit.
                if "comfoairq" in device_name:
                    ventilation_uuid = device.get("uuid")
                    _LOGGER.info(
                        "Found ventilation unit: %s with UUID: %s",
                        device_name,
                        ventilation_uuid,
                    )

                # Search for the ComfoClime unit.
                elif "comfoclime" in device_name:
                    clime_uuid = device.get("uuid")
                    _LOGGER.info(
                        "Found ComfoClime unit: %s with UUID: %s",
                        device_name,
                        clime_uuid,
                    )

            if not ventilation_uuid or not clime_uuid:
                _LOGGER.error("Could not find required devices: Ventilation or Clime")
                return None

            return {"ventilation_uuid": ventilation_uuid, "clime_uuid": clime_uuid}
    except aiohttp.ClientError as e:
        _LOGGER.error("Error fetching devices: %s", e)
        return None


class ComfoClimeClimate(ClimateEntity):
    """Climate entity for ComfoClime."""

    def __init__(
        self,
        hass: HomeAssistant,
        ip_address: str,
        system_uuid: str,
        device_uuids: dict,
    ) -> None:
        """Initialize the ComfoClimeClimate entity."""
        self.hass = hass
        self._ip_address = ip_address
        self._system_uuid = system_uuid
        self._clime_uuid = device_uuids["clime_uuid"]
        self._ventilation_uuid = device_uuids["ventilation_uuid"]

        """Set the unique ID and name."""
        self._unique_id = f"comfoclime_{system_uuid}"
        self._name = "ComfoClime Climate"

        """Initialize entity attributes."""
        self._temperature_profile = None
        self._fan_speed = 2
        self._hvac_mode = HVACMode.HEAT
        self._preset_mode = "comfort"
        self._fan_modes = ["off", "low", "medium", "high"]
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._available = True

        """.Set the supported features without _attr_."""
        self.supported_features = (
            ClimateEntityFeature.PRESET_MODE
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.TURN_OFF
        )

    @property
    def name(self) -> str:
        """Return the name of the climate entity."""
        return self._name

    @property
    def unique_id(self) -> str | None:
        """Return the unique ID of the climate entity."""
        return self._unique_id

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the list of supported HVAC modes."""
        return [HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF]

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the current HVAC mode."""
        return self._hvac_mode

    @property
    def preset_modes(self) -> list[str] | None:
        """Return the list of available preset modes."""
        return ["comfort", "eco", "power"]

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        return self._preset_mode

    @property
    def fan_modes(self) -> list[str] | None:
        """Return the list of available fan modes."""
        return self._fan_modes

    @property
    def fan_mode(self) -> str | None:
        """Return the current fan mode."""
        return self._map_fan_speed_to_mode(self._fan_speed)

    async def async_update(self) -> None:
        """Fetch the latest data from the device."""
        _LOGGER.debug("Updating ComfoClime data")
        try:
            await self._fetch_clime_data()
            self._available = True
        except aiohttp.ClientError as e:
            _LOGGER.error("Update failed: %s", e)
            self._available = False

        # Check if the entity is fully registered in Home Assistant.
        if self.hass is not None and self.entity_id:
            self.async_write_ha_state()
        else:
            _LOGGER.warning(
                "Entity not fully initialized, skipping async_write_ha_state"
            )

    async def _fetch_clime_data(self):
        """Fetch data for the climate unit."""
        url = f"http://{self._ip_address}/device/{self._clime_uuid}/definition"
        headers = {"Authorization": "Bearer null"}
        async with (
            aiohttp.ClientSession() as session,
            session.get(url, headers=headers) as response,
        ):
            if response.status == 200:
                data = await response.json()

                # Update temperature profile (preset mode).
                self._temperature_profile = data.get("temperatureProfile")
                _LOGGER.debug(
                    "Fetched temperature profile: %s", self._temperature_profile
                )

                # Adjust the preset mode based on the retrieved temperature profile value.
                if self._temperature_profile == 0:
                    self._preset_mode = "comfort"
                elif self._temperature_profile == 1:
                    self._preset_mode = "power"
                elif self._temperature_profile == 2:
                    self._preset_mode = "eco"
                elif self._temperature_profile == 3:
                    self._hvac_mode = HVACMode.COOL
                else:
                    self._preset_mode = None

                # Update the HVAC mode based on the temperature profile.
                if self._temperature_profile in [0, 1, 2]:
                    self._hvac_mode = HVACMode.HEAT
                elif self._temperature_profile == 3:
                    self._hvac_mode = HVACMode.COOL
                else:
                    self._hvac_mode = HVACMode.OFF

                _LOGGER.debug(
                    "Updated preset mode: %s, HVAC mode: %s",
                    self._preset_mode,
                    self._hvac_mode,
                )

    async def _fetch_ventilation_data(self):
        """Fetch data for the ventilation unit."""
        url = f"http://{self._ip_address}/device/{self._ventilation_uuid}/definition"
        headers = {"Authorization": "Bearer null"}
        async with (
            aiohttp.ClientSession() as session,
            session.get(url, headers=headers) as response,
        ):
            if response.status == 200:
                data = await response.json()
                self._fan_speed = data.get("fanSpeed")
                _LOGGER.debug("Fetched ventilation data: %s", data)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode for the climate entity."""
        if hvac_mode == HVACMode.COOL:
            await self._async_set_temperature_profile(3)
        elif hvac_mode == HVACMode.HEAT:
            await self._async_set_temperature_profile(0)
        else:
            await self._async_set_temperature_profile(4)
        self._hvac_mode = hvac_mode
        await self.async_update()

    async def async_set_ppreset_mode(self, preset_mode: str) -> None:
        """Set the preset mode for the climate entity."""
        if preset_mode == "comfort":
            await self._async_set_temperature_profile(0)
        elif preset_mode == "eco":
            await self._async_set_temperature_profile(2)
        elif preset_mode == "power":
            await self._async_set_temperature_profile(1)
        self._preset_mode = preset_mode
        await self.async_update()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode for the climate entity."""
        speed = self._map_fan_mode_to_speed(fan_mode)
        success = await self._async_set_fan_speed(speed)
        if success:
            self._fan_speed = speed
            await self.async_update()

    async def _async_set_temperature_profile(self, profile):
        url = f"http://{self._ip_address}/device"
        payload = {
            "uuid": self._clime_uuid,
            "systemUuid": self._system_uuid,
            "temperatureProfile": profile,
        }
        headers = {"Authorization": "Bearer null"}
        async with aiohttp.ClientSession() as session:
            await session.put(url, json=payload, headers=headers)

    async def _async_set_fan_speed(self, speed):
        url = f"http://{self._ip_address}/device"
        payload = {
            "uuid": self._ventilation_uuid,
            "systemUuid": self._system_uuid,
            "fanSpeed": speed,
        }
        headers = {"Authorization": "Bearer null"}
        async with (
            aiohttp.ClientSession() as session,
            session.put(url, json=payload, headers=headers) as response,
        ):
            return response.status == 200

    def _map_fan_mode_to_speed(self, fan_mode):
        return {"off": 0, "low": 1, "medium": 2, "high": 3}.get(fan_mode, 2)

    def _map_fan_speed_to_mode(self, speed):
        return {0: "off", 1: "low", 2: "medium", 3: "high"}.get(speed, "medium")
