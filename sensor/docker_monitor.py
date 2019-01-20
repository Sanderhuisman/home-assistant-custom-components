'''
Docker Monitor component

For more details about this component, please refer to the documentation at
https://github.com/Sanderhuisman/home-assistant-custom-components
'''
import logging
from datetime import timedelta

import homeassistant.util.dt as dt_util
from homeassistant.const import ATTR_ATTRIBUTION, EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers.entity import Entity

from custom_components.docker_monitor import (
    CONF_ATTRIBUTION,
    DOCKER_HANDLE,
    DATA_DOCKER_API,
    DATA_SENSOR_CONDITIONS,
    _UTILISATION_MON_COND,
    _CONTAINER_MON_COND,

    UTILISATION_MONITOR_VERSION,
    CONTAINER_MONITOR_STATUS,
    CONTAINER_MONITOR_MEMORY_USAGE,
    CONTAINER_MONITOR_MEMORY_PERCENTAGE,
    CONTAINER_MONITOR_CPU_PERCENTAGE,
    CONTAINER_MONITOR_NETWORK_UP,
    CONTAINER_MONITOR_NETWORK_DOWN,
)

DEPENDENCIES = ['docker_monitor']

_LOGGER = logging.getLogger(__name__)

ATTR_VERSION_API = 'Api_version'
ATTR_VERSION_OS = 'Os'
ATTR_VERSION_ARCH = 'Architecture'
ATTR_ONLINE_CPUS = 'Online_CPUs'
ATTR_MEMORY_LIMIT = 'Memory_limit'
ATTR_CREATED = 'Created'
ATTR_STARTED_AT = 'Started_at'


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Docker Monitor Sensor."""

    api = hass.data[DOCKER_HANDLE][DATA_DOCKER_API]
    monitored_conditions = hass.data[DOCKER_HANDLE][DATA_SENSOR_CONDITIONS]

    interval = 10  # todo
    # interval                = config.get(CONF_SCAN_INTERVAL).total_seconds()

    version = api.get_info()
    _LOGGER.info("Docker version: {}".format(version.get('version', None)))

    sensors = [DockerUtilSensor(api, variable, interval)
               for variable in monitored_conditions if variable in _UTILISATION_MON_COND]

    for name in [x.get_name() for x in api.get_containers()]:
        sensors += [DockerContainerSensor(api, name, variable, interval)
                    for variable in monitored_conditions if variable in _CONTAINER_MON_COND]

    if sensors:
        add_entities(sensors, True)


class DockerUtilSensor(Entity):
    """Representation of a Docker Sensor."""

    def __init__(self, api, variable, interval):
        """Initialize the sensor."""
        self._api = api
        self._interval = interval  # TODO implement

        self._var_id = variable
        self._var_name = _UTILISATION_MON_COND[variable][0]
        self._var_unit = _UTILISATION_MON_COND[variable][1]
        self._var_icon = _UTILISATION_MON_COND[variable][2]

        self._state = None
        self._attributes = {
            ATTR_ATTRIBUTION: CONF_ATTRIBUTION
        }

        _LOGGER.info(
            "Initializing utilization sensor \"{}\"".format(self._var_id))

    @property
    def name(self):
        """Return the name of the sensor."""
        return "Docker {}".format(self._var_name)

    @property
    def icon(self):
        """Icon to use in the frontend."""
        return self._var_icon

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        return self._var_unit

    def update(self):
        """Get the latest data for the states."""
        if self._var_id == UTILISATION_MONITOR_VERSION:
            version = self._api.get_info()
            self._state = version.get('version', None)
            self._attributes[ATTR_VERSION_API] = version.get(
                'api_version', None)
            self._attributes[ATTR_VERSION_OS] = version.get('os', None)
            self._attributes[ATTR_VERSION_ARCH] = version.get('arch', None)

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return self._attributes


class DockerContainerSensor(Entity):
    """Representation of a Docker Sensor."""

    def __init__(self, api, name, variable, interval):
        """Initialize the sensor."""
        self._api = api
        self._name = name
        self._interval = interval

        self._var_id = variable
        self._var_name = _CONTAINER_MON_COND[variable][0]
        self._var_unit = _CONTAINER_MON_COND[variable][1]
        self._var_icon = _CONTAINER_MON_COND[variable][2]

        self._state = None
        self._attributes = {
            ATTR_ATTRIBUTION: CONF_ATTRIBUTION
        }

        self._container = api.get_container(name)

        _LOGGER.info("Initializing Docker sensor \"{}\" with parameter: {}".format(
            self._name, self._var_name))

        def update_callback(stats):
            _LOGGER.debug("Received callback with message: {}".format(stats))

            state = None
            if self._var_id == CONTAINER_MONITOR_STATUS:
                state = stats['info']['status']
            # cpu
            elif self._var_id == CONTAINER_MONITOR_CPU_PERCENTAGE:
                state = stats.get('cpu', {}).get('total')
            # memory
            elif self._var_id == CONTAINER_MONITOR_MEMORY_USAGE:
                use = stats.get('memory', {}).get('usage')
                state = None
                if use is not None:
                    state = round(use / (1024 ** 2))  # Bytes to MB
            elif self._var_id == CONTAINER_MONITOR_MEMORY_PERCENTAGE:
                state = stats.get('memory', {}).get('usage_percent')
            # network
            elif self._var_id == CONTAINER_MONITOR_NETWORK_UP:
                up = stats.get('network', {}).get('total_tx')
                if up is not None:
                    state = round(up / (1024 ** 2))
            elif self._var_id == CONTAINER_MONITOR_NETWORK_DOWN:
                down = stats.get('network', {}).get('total_rx')
                if down is not None:
                    state = round(down / (1024 ** 2))
            self._state = state

            # Attributes
            if self._var_id in (CONTAINER_MONITOR_CPU_PERCENTAGE):
                cpus = stats.get('cpu', {}).get('online_cpus')
                if cpus is not None:
                    self._attributes[ATTR_ONLINE_CPUS] = cpus
            elif self._var_id in (CONTAINER_MONITOR_MEMORY_USAGE, CONTAINER_MONITOR_MEMORY_PERCENTAGE):
                limit = stats.get('memory', {}).get('limit')
                if limit is not None:
                    self._attributes[ATTR_MEMORY_LIMIT] = str(
                        round(limit / (1024 ** 2))) + ' MB'

            self._attributes[ATTR_CREATED] = dt_util.as_local(
                stats['info']['created']).isoformat()
            self._attributes[ATTR_STARTED_AT] = dt_util.as_local(
                stats['info']['started']).isoformat()

            self.schedule_update_ha_state()

        self._container.stats(update_callback, self._interval)

    @property
    def name(self):
        """Return the name of the sensor, if any."""
        return "Docker {} {}".format(self._name, self._var_name)

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        if self._var_id == CONTAINER_MONITOR_STATUS:
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
    def unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        return self._var_unit

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return self._attributes
