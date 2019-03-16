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
from homeassistant.core import callback

from .const import (
    CONF_ATTRIBUTION,
    CONF_CONTAINERS,
    CONTAINER_INFO,
    CONTAINER_INFO_STATUS,
    DATA_CONFIG,
    DATA_DOCKER_API,
    DOCKER_HANDLE,
    ICON_SWITCH,
    UPDATE_TOPIC,
)

VERSION = '0.0.2'

DEPENDENCIES = ['docker_monitor']

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Docker Monitor Switch."""

    api = hass.data[DOCKER_HANDLE][DATA_DOCKER_API]
    config = hass.data[DOCKER_HANDLE][DATA_CONFIG]
    clientname = config[CONF_NAME]

    switches = [ContainerSwitch(clientname, api.get_containers()[name])
                for name in config[CONF_CONTAINERS] if name in api.get_containers()]

    if switches:
        async_add_entities(switches)
    else:
        _LOGGER.info("No containers setup")


class ContainerSwitch(SwitchDevice):
    def __init__(self, clientname, container):
        self._clientname = clientname
        self._container = container

        self._state = False

    @property
    def name(self):
        """Return the name of the sensor."""
        return "{} {}".format(self._clientname, self._container.get_name())

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

    def turn_on(self, **kwargs):
        self._container.start()

    def turn_off(self, **kwargs):
        self._container.stop()

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.hass.helpers.dispatcher.async_dispatcher_connect(
            UPDATE_TOPIC, self.async_update_callback)

    @callback
    def async_update_callback(self):
        """Update callback."""

        state = self._container.get_info()[CONTAINER_INFO_STATUS] == 'running'
        if state is not self._state:
            self._state = state
            self.async_schedule_update_ha_state()
