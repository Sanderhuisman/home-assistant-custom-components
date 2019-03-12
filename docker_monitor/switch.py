'''
Docker Monitor component

For more details about this component, please refer to the documentation at
https://github.com/Sanderhuisman/home-assistant-custom-components
'''
import logging

from homeassistant.components.switch import (
    ENTITY_ID_FORMAT,
    PLATFORM_SCHEMA,
    SwitchDevice
)
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    CONF_NAME
)
from homeassistant.core import ServiceCall

from .const import (
    CONF_ATTRIBUTION,
    CONF_CONTAINERS,
    CONTAINER_INFO,
    CONTAINER_INFO_STATUS,
    DATA_CONFIG,
    DATA_DOCKER_API,
    DOCKER_HANDLE,
    ICON_SWITCH
)

VERSION = '0.0.2'

DEPENDENCIES = ['docker_monitor']

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass, config, async_add_entities, discovery_info=None
):  # pylint: disable=unused-argument
    """Set up the Docker Monitor Switch."""

    api = hass.data[DOCKER_HANDLE][DATA_DOCKER_API]
    config = hass.data[DOCKER_HANDLE][DATA_CONFIG]
    clientname = config[CONF_NAME]

    containers = [container.get_name() for container in api.get_containers()]
    switches = [ContainerSwitch(api, clientname, name)
                for name in config[CONF_CONTAINERS] if name in containers]
    if switches:
        async_add_entities(switches, False)
        return True
    else:
        _LOGGER.info("No containers setup")
        return False


class ContainerSwitch(SwitchDevice):
    def __init__(self, api, clientname, container_name):
        self._api = api
        self._clientname = clientname
        self._container_name = container_name
        self._state = False

        self._container = api.get_container(container_name)

        def update_callback(stats):
            _LOGGER.debug("Received callback with message: {}".format(stats))

            if stats[CONTAINER_INFO][CONTAINER_INFO_STATUS] == 'running':
                state = True
            else:
                state = False

            if self._state is not state:
                self._state = state

                self.schedule_update_ha_state()

        self._container.stats(update_callback)

    async def async_update(self):
        pass

    @property
    def name(self):
        """Return the name of the sensor."""
        return "{} {}".format(self._clientname, self._container_name)

    @property
    def should_poll(self):
        return False

    @property
    def icon(self):
        return ICON_SWITCH

    @property
    def device_state_attributes(self):
        return {
            ATTR_ATTRIBUTION: CONF_ATTRIBUTION
        }

    @property
    def is_on(self):
        return self._state

    async def async_turn_on(self, **kwargs):  # pylint: disable=unused-argument
        """Turn on the switch."""
        self._container.start()

    async def async_turn_off(self, **kwargs):  # pylint: disable=unused-argument
        self._container.stop()
