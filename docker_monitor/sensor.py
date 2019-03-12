'''
Docker Monitor component

For more details about this component, please refer to the documentation at
https://github.com/Sanderhuisman/home-assistant-custom-components
'''
import logging
from datetime import timedelta

import homeassistant.util.dt as dt_util
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    CONF_MONITORED_CONDITIONS,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    EVENT_HOMEASSISTANT_STOP
)
from homeassistant.helpers.entity import Entity

from .const import (
    ATTR_CREATED,
    ATTR_IMAGE,
    ATTR_MEMORY_LIMIT,
    ATTR_ONLINE_CPUS,
    ATTR_STARTED_AT,
    ATTR_VERSION_API,
    ATTR_VERSION_ARCH,
    ATTR_VERSION_OS,
    CONF_ATTRIBUTION,
    CONF_CONTAINERS,
    CONF_MONITOR_CONTAINER_CONDITIONS,
    CONF_MONITOR_CONTAINER_CPU_PERCENTAGE,
    CONF_MONITOR_CONTAINER_IMAGE,
    CONF_MONITOR_CONTAINER_MEMORY_PERCENTAGE,
    CONF_MONITOR_CONTAINER_MEMORY_USAGE,
    CONF_MONITOR_CONTAINER_NETWORK_SPEED_DOWN,
    CONF_MONITOR_CONTAINER_NETWORK_SPEED_UP,
    CONF_MONITOR_CONTAINER_NETWORK_TOTAL_DOWN,
    CONF_MONITOR_CONTAINER_NETWORK_TOTAL_UP,
    CONF_MONITOR_CONTAINER_STATUS,
    CONF_MONITOR_CONTAINER_UPTIME,
    CONF_MONITOR_UTILISATION_CONDITIONS,
    CONF_MONITOR_UTILISATION_VERSION,
    CONTAINER_INFO,
    CONTAINER_INFO_CREATED,
    CONTAINER_INFO_ID,
    CONTAINER_INFO_IMAGE,
    CONTAINER_INFO_STARTED,
    CONTAINER_INFO_STATUS,
    DATA_CONFIG,
    DATA_DOCKER_API,
    DOCKER_HANDLE, PRECISION,
    VERSION_INFO_API_VERSION,
    VERSION_INFO_ARCHITECTURE,
    VERSION_INFO_KERNEL,
    VERSION_INFO_OS,
    VERSION_INFO_VERSION
)

VERSION = '0.0.2'

DEPENDENCIES = ['docker_monitor']

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass, config, async_add_entities, discovery_info=None
):  # pylint: disable=unused-argument
    """Set up the Docker Monitor Sensor."""

    api = hass.data[DOCKER_HANDLE][DATA_DOCKER_API]
    config = hass.data[DOCKER_HANDLE][DATA_CONFIG]
    clientname = config[CONF_NAME]
    interval = config[CONF_SCAN_INTERVAL].total_seconds()

    sensors = [DockerUtilSensor(api, clientname, variable, interval)
               for variable in config[CONF_MONITORED_CONDITIONS] if variable in CONF_MONITOR_UTILISATION_CONDITIONS]

    containers = [container.get_name() for container in api.get_containers()]
    for name in config[CONF_CONTAINERS]:
        if name in containers:
            sensors += [DockerContainerSensor(api, clientname, name, variable, interval)
                        for variable in config[CONF_MONITORED_CONDITIONS] if variable in CONF_MONITOR_CONTAINER_CONDITIONS]

    if sensors:
        async_add_entities(sensors, True)
    else:
        _LOGGER.info("No containers setup")
        return False


class DockerUtilSensor(Entity):
    """Representation of a Docker Sensor."""

    def __init__(self, api, clientname, variable, interval):
        """Initialize the sensor."""
        self._api = api
        self._clientname = clientname
        self._interval = interval  # TODO implement

        self._var_id = variable
        self._var_name = CONF_MONITOR_UTILISATION_CONDITIONS[variable][0]
        self._var_unit = CONF_MONITOR_UTILISATION_CONDITIONS[variable][1]
        self._var_icon = CONF_MONITOR_UTILISATION_CONDITIONS[variable][2]
        self._var_class = CONF_MONITOR_UTILISATION_CONDITIONS[variable][3]

        self._state = None
        self._attributes = {
            ATTR_ATTRIBUTION: CONF_ATTRIBUTION
        }

        _LOGGER.info(
            "Initializing utilization sensor \"{}\"".format(self._var_id))

    @property
    def name(self):
        """Return the name of the sensor."""
        return "{} {}".format(self._clientname, self._var_name)

    @property
    def icon(self):
        """Icon to use in the frontend."""
        return self._var_icon

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def device_class(self):
        """Return the class of this sensor."""
        return self._var_class

    @property
    def unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        return self._var_unit

    # async def async_update(self):
    # # def update(self):
    #     """Get the latest data for the states."""
    #     if self._var_id == CONF_MONITOR_UTILISATION_VERSION:
    #         version = self._api.get_info()
    #         self._state = version.get(
    #             VERSION_INFO_VERSION, None)
    #         self._attributes[ATTR_VERSION_API] = version.get(
    #             VERSION_INFO_API_VERSION, None)
    #         self._attributes[ATTR_VERSION_OS] = version.get(
    #             VERSION_INFO_OS, None)
    #         self._attributes[ATTR_VERSION_ARCH] = version.get(
    #             VERSION_INFO_ARCHITECTURE, None)

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return self._attributes


class DockerContainerSensor(Entity):
    """Representation of a Docker Sensor."""

    def __init__(self, api, clientname, container_name, variable, interval):
        """Initialize the sensor."""
        self._api = api
        self._clientname = clientname
        self._container_name = container_name
        self._interval = interval

        self._var_id = variable
        self._var_name = CONF_MONITOR_CONTAINER_CONDITIONS[variable][0]
        self._var_unit = CONF_MONITOR_CONTAINER_CONDITIONS[variable][1]
        self._var_icon = CONF_MONITOR_CONTAINER_CONDITIONS[variable][2]
        self._var_class = CONF_MONITOR_CONTAINER_CONDITIONS[variable][3]

        self._state = None
        self._attributes = {
            ATTR_ATTRIBUTION: CONF_ATTRIBUTION
        }

        self._container = api.get_container(container_name)

        _LOGGER.info("Initializing Docker sensor \"{}\" with parameter: {}".format(
            self._container_name, self._var_name))

        def update_callback(stats):
            state = None
            # Info
            if self._var_id == CONF_MONITOR_CONTAINER_STATUS:
                state = stats[CONTAINER_INFO][CONTAINER_INFO_STATUS]
            elif self._var_id == CONF_MONITOR_CONTAINER_UPTIME:
                up_time = stats.get(CONTAINER_INFO, {}).get(
                    CONTAINER_INFO_STARTED)
                if up_time is not None:
                    state = dt_util.as_local(up_time).isoformat()
            elif self._var_id == CONF_MONITOR_CONTAINER_IMAGE:
                # get first from array
                state = stats[CONTAINER_INFO][CONTAINER_INFO_IMAGE][0]
            # cpu
            elif self._var_id == CONF_MONITOR_CONTAINER_CPU_PERCENTAGE:
                state = stats.get('cpu', {}).get('total')
            # memory
            elif self._var_id == CONF_MONITOR_CONTAINER_MEMORY_USAGE:
                use = stats.get('memory', {}).get('usage')
                if use is not None:
                    state = round(use / (1024 ** 2), PRECISION)  # Bytes to MB
            elif self._var_id == CONF_MONITOR_CONTAINER_MEMORY_PERCENTAGE:
                state = stats.get('memory', {}).get('usage_percent')
            # network
            elif self._var_id == CONF_MONITOR_CONTAINER_NETWORK_SPEED_UP:
                up = stats.get('network', {}).get('speed_tx')
                state = None
                if up is not None:
                    state = round(up / (1024), PRECISION)  # Bytes to kB
            elif self._var_id == CONF_MONITOR_CONTAINER_NETWORK_SPEED_DOWN:
                down = stats.get('network', {}).get('speed_rx')
                if down is not None:
                    state = round(down / (1024), PRECISION)
            elif self._var_id == CONF_MONITOR_CONTAINER_NETWORK_TOTAL_UP:
                up = stats.get('network', {}).get('total_tx') # Bytes to kB
                if up is not None:
                    state = round(up / (1024 ** 2), PRECISION)
            elif self._var_id == CONF_MONITOR_CONTAINER_NETWORK_TOTAL_DOWN:
                down = stats.get('network', {}).get('total_rx')
                if down is not None:
                    state = round(down / (1024 ** 2), PRECISION)

            self._state = state

            # Attributes
            if self._var_id in (CONF_MONITOR_CONTAINER_STATUS):
                self._attributes[ATTR_IMAGE] = state = stats[CONTAINER_INFO][CONTAINER_INFO_IMAGE][0]
                self._attributes[ATTR_CREATED] = dt_util.as_local(
                    stats[CONTAINER_INFO][CONTAINER_INFO_CREATED]).isoformat()
                self._attributes[ATTR_STARTED_AT] = dt_util.as_local(
                    stats[CONTAINER_INFO][CONTAINER_INFO_STARTED]).isoformat()
            elif self._var_id in (CONF_MONITOR_CONTAINER_CPU_PERCENTAGE):
                cpus = stats.get('cpu', {}).get('online_cpus')
                if cpus is not None:
                    self._attributes[ATTR_ONLINE_CPUS] = cpus
            elif self._var_id in (CONF_MONITOR_CONTAINER_MEMORY_USAGE, CONF_MONITOR_CONTAINER_MEMORY_PERCENTAGE):
                limit = stats.get('memory', {}).get('limit')
                if limit is not None:
                    self._attributes[ATTR_MEMORY_LIMIT] = str(
                        round(limit / (1024 ** 2), PRECISION)) + ' MB'

            self.schedule_update_ha_state()

        self._container.stats(update_callback, self._interval)

    # async def async_update(self):

    @property
    def name(self):
        """Return the name of the sensor, if any."""
        return "{} {} {}".format(self._clientname, self._container_name, self._var_name)

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        if self._var_id == CONF_MONITOR_CONTAINER_STATUS:
            if self._state == 'running':
                return 'mdi:checkbox-marked-circle-outline'
            else:
                return 'mdi:checkbox-blank-circle-outline'
        else:
            return self._var_icon

    @property
    def should_poll(self):
        return False

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def device_class(self):
        """Return the class of this sensor."""
        return self._var_class

    @property
    def unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        return self._var_unit

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return self._attributes
