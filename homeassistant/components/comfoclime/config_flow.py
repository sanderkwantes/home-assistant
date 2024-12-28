"""Config flow for the ComfoClime integration."""

import asyncio
import ipaddress
import logging

import aiohttp
from aiohttp import ClientTimeout
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_IP_ADDRESS

_LOGGER = logging.getLogger(__name__)

DOMAIN = "comfoclime"


class ComfoClimeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for ComfoClime integration."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                return await self._test_connection(user_input[CONF_IP_ADDRESS])
            except (aiohttp.ClientError, TimeoutError, ValueError) as err:
                _LOGGER.error("Unexpected error: %s", err)
                errors["base"] = "unknown"

        # Automatically scan the network
        session = aiohttp.ClientSession()
        ip_address = await self._scan_network_for_comfoclime(session)
        await session.close()

        if ip_address:
            return await self._test_connection(ip_address)

        # If no device is found, prompt for manual input
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_IP_ADDRESS): str}),
            errors={"base": "device_not_found"},
        )

    async def _test_connection(
        self, ip_address: str
    ) -> config_entries.ConfigFlowResult:
        """Test the connection with the given IP address."""
        _LOGGER.info("Try to connect to %s", ip_address)
        async with aiohttp.ClientSession() as session:
            try:
                timeout = ClientTimeout(total=10)  # Correct timeout fix
                async with session.get(
                    f"http://{ip_address}/system/systems", timeout=timeout
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if "systems" in data:
                            _LOGGER.info(
                                "Successful connection to ComfoClime at %s", ip_address
                            )
                            return self.async_create_entry(
                                title=f"ComfoClime ({ip_address})",
                                data={CONF_IP_ADDRESS: ip_address},
                            )
            except (aiohttp.ClientError, TimeoutError) as e:
                _LOGGER.error("Error testing connection: %s", e)

        _LOGGER.warning("Cannot connect to the provided IP address")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_IP_ADDRESS): str}),
            errors={"base": "cannot_connect"},
        )

    async def _scan_network_for_comfoclime(
        self, session: aiohttp.ClientSession
    ) -> str | None:
        """Scan the network for a ComfoClime device."""
        local_ip = getattr(self.hass.config.api, "local_ip", None)

        if not local_ip:
            _LOGGER.error("Cannot determine the local IP address of Home Assistant")
            return None

        subnet = ".".join(local_ip.split(".")[:3]) + ".0/24"
        _LOGGER.info("Start network scan in subnet: %s", subnet)

        net = ipaddress.ip_network(subnet, strict=False)
        tasks = [check_comfoclime_api(str(ip), session) for ip in net.hosts()]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for idx, result in enumerate(results):
            ip = list(net.hosts())[idx]
            if isinstance(result, str):
                _LOGGER.info("ComfoClime found at IP: %s", result)
                return result
            if isinstance(result, Exception):
                _LOGGER.debug("Error scanning %s: %s", ip, result)
            else:
                _LOGGER.debug("No ComfoClime found at %s", ip)

        _LOGGER.info("No ComfoClime device found during the network scan")
        return None


async def check_comfoclime_api(ip: str, session: aiohttp.ClientSession) -> str | None:
    """Check if the device at this IP has a ComfoClime API."""
    url = f"http://{ip}/system/systems"
    headers = {"Authorization": "Bearer null"}
    timeout = ClientTimeout(total=10)

    try:
        _LOGGER.debug("Trying to connect to %s", ip)
        async with session.get(url, headers=headers, timeout=timeout) as response:
            if response.status == 200:
                data = await response.json()
                if "systems" in data:
                    _LOGGER.info("ComfoClime found at %s", ip)
                    return str(ip)
    except (aiohttp.ClientError, TimeoutError, ValueError) as e:
        _LOGGER.info("Error connecting to %s: %s", ip, e)

    return None
