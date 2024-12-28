"""ComfoClime integration for Home Assistant."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)
DOMAIN = "comfoclime"

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant | None, config: ConfigType) -> bool:
    """Set up ComfoClime integration using YAML (if any)."""
    return True


async def async_setup_entry(hass: HomeAssistant | None, entry: ConfigEntry) -> bool:
    """Set up ComfoClime from a config entry."""
    if hass is None:
        _LOGGER.error("HomeAssistant instance is None")
        return False

    await hass.config_entries.async_forward_entry_setups(entry, ["climate", "sensor"])
    return True


async def async_unload_entry(hass: HomeAssistant | None, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if hass is None:
        _LOGGER.error("HomeAssistant instance is None")
        return False

    await hass.config_entries.async_forward_entry_unload(entry, "climate")
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    return True
