'''
Docker Monitor component

For more details about this component, please refer to the documentation at
https://github.com/Sanderhuisman/home-assistant-custom-components
'''
import logging
import time

import voluptuous as vol
from homeassistant.const import (
    CONF_HOSTS,
    CONF_MONITORED_CONDITIONS,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_SENSORS,
    CONF_URL,
    EVENT_HOMEASSISTANT_STOP
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.discovery import load_platform
from homeassistant.util import slugify as util_slugify

from .const import (
    CONF_CONTAINERS,
    CONF_EVENTS,
    CONF_MONITOR_CONTAINER_CONDITIONS,
    CONF_MONITOR_UTILISATION_CONDITIONS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_CONTAINER,
    PLATFORMS
)
from .helpers import DockerMonitorApi

VERSION = '0.0.2'

REQUIREMENTS = ['docker==3.7.0', 'python-dateutil==2.7.5']

_LOGGER = logging.getLogger(__name__)

CONF_MONITOR_UTILISATION_CONDITIONS_KEYS = list(
    CONF_MONITOR_UTILISATION_CONDITIONS.keys())
CONF_MONITOR_CONTAINER_CONDITIONS_KEYS = list(
    CONF_MONITOR_CONTAINER_CONDITIONS.keys())

CONTAINER_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME):
        cv.string,
    vol.Optional(CONF_SENSORS, default=CONF_MONITOR_CONTAINER_CONDITIONS_KEYS):
        vol.All(cv.ensure_list, [
                vol.In(CONF_MONITOR_CONTAINER_CONDITIONS_KEYS)]),
})

SERVER_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME):
        cv.string,
    vol.Required(CONF_URL):
        cv.string,
    vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL):
        cv.time_period,
    vol.Optional(CONF_EVENTS, default=False):
        cv.boolean,
    vol.Optional(CONF_MONITORED_CONDITIONS, default=CONF_MONITOR_UTILISATION_CONDITIONS_KEYS):
        vol.All(cv.ensure_list, [
                vol.In(CONF_MONITOR_UTILISATION_CONDITIONS_KEYS)]),
    vol.Optional(CONF_CONTAINERS):
        {cv.string: CONTAINER_SCHEMA}
})

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_HOSTS):
            vol.All(cv.ensure_list, [SERVER_SCHEMA]),
    }),
}, extra=vol.ALLOW_EXTRA)


def setup(hass, config):
    _LOGGER.debug("Settings: {}".format(config[DOMAIN]))

    hass.data[DOMAIN] = {}
    for host in config[DOMAIN][CONF_HOSTS]:
        name = host[CONF_NAME]

        try:
            if host[CONF_EVENTS]:
                def event_listener(message):
                    event = util_slugify("{} {}".format(name, EVENT_CONTAINER))
                    _LOGGER.info(
                        "Sending event {} notification with message {}".format(event, message))
                    hass.bus.fire(event, message)

                api = DockerMonitorApi(host[CONF_URL], event_listener)
            else:
                api = DockerMonitorApi(host[CONF_URL])
        except (ImportError, ConnectionError) as e:
            _LOGGER.info("Error setting up Docker API ({})".format(e))
            return False
        else:
            hass.data[DOMAIN][name] = api

            for component in PLATFORMS:
                load_platform(hass, component, DOMAIN, host, config)

            api.start()

    def monitor_stop(_service_or_event):
        """Stop the monitor threads."""
        _LOGGER.info("Stopping threads for Docker monitor")
        for api in hass.data[DOMAIN].values():
            api.exit()

    hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, monitor_stop)

    return True
