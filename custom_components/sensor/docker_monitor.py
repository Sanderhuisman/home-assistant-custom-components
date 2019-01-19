import logging
from datetime import timedelta

import threading
import time

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    CONF_HOST,
    CONF_MONITORED_CONDITIONS,
    EVENT_HOMEASSISTANT_STOP
)
from homeassistant.helpers.entity import Entity
import homeassistant.util.dt as dt_util


REQUIREMENTS = ['docker==3.7.0', 'python-dateutil==2.7.5']

_LOGGER = logging.getLogger(__name__)

DEFAULT_HOST        = 'unix://var/run/docker.sock'
CONF_CONTAINERS     = 'containers'

CONF_ATTRIBUTION    = 'Data provided by Docker'

ATTR_VERSION_API    = 'Api_version'
ATTR_VERSION_OS     = 'Os'
ATTR_VERSION_ARCH   = 'Architecture'
ATTR_ONLINE_CPUS    = 'Online_CPUs'
ATTR_MEMORY_LIMIT   = 'Memory_limit'
ATTR_CREATED        = 'Created'
ATTR_STARTED_AT     = 'Started_at'

PRECISION           = 2

UTILISATION_MONITOR_VERSION         = 'utilization_version'

CONTAINER_MONITOR_STATUS            = 'container_status'
CONTAINER_MONITOR_MEMORY_USAGE      = 'container_memory_usage'
CONTAINER_MONITOR_MEMORY_PERCENTAGE = 'container_memory_percentage_usage'
CONTAINER_MONITOR_CPU_PERCENTAGE    = 'container_cpu_percentage_usage'

_UTILISATION_MON_COND = {
    UTILISATION_MONITOR_VERSION         : ['Version'                , None      , 'mdi:memory'],
}

_CONTAINER_MON_COND = {
    CONTAINER_MONITOR_STATUS            : ['Status'                 , None      , 'mdi:checkbox-marked-circle-outline'  ],
    CONTAINER_MONITOR_MEMORY_USAGE      : ['Memory use'             , 'MB'      , 'mdi:memory'                          ],
    CONTAINER_MONITOR_MEMORY_PERCENTAGE : ['Memory use (percent)'   , '%'       , 'mdi:memory'                          ],
    CONTAINER_MONITOR_CPU_PERCENTAGE    : ['CPU use'                , '%'       , 'mdi:chip'                            ],
}

_MONITORED_CONDITIONS = list(_UTILISATION_MON_COND.keys()) + \
    list(_CONTAINER_MON_COND.keys())

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_HOST, default=DEFAULT_HOST): cv.string,
    vol.Optional(CONF_MONITORED_CONDITIONS): vol.All(cv.ensure_list, [vol.In(_MONITORED_CONDITIONS)]),
    vol.Optional(CONF_CONTAINERS): cv.ensure_list,
})

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Synology NAS Sensor."""
    import docker

    host                    = config.get(CONF_HOST)
    monitored_conditions    = config.get(CONF_MONITORED_CONDITIONS)

    try:
        api = docker.DockerClient(base_url=host)
    except:  # noqa: E722 pylint: disable=bare-except
        _LOGGER.info("Error setting up Docker sensor")
        return

    version = dockerVersion(api)
    _LOGGER.info("Docker version: {}".format(version.get('version', None)))

    threads = {}

    sensors = [DockerUtilSensor(api, variable) for variable in monitored_conditions if variable in _UTILISATION_MON_COND]

    containers      = api.containers.list(all=True) or []
    container_names = [x.name for x in containers]
    for container in containers:
        _LOGGER.debug("Found container: {}".format(container.name))

    for container_name in config.get(CONF_CONTAINERS, container_names):
        thread = DockerContainerApi(container_name, api)
        threads[container_name] = thread
        thread.start()

        sensors += [DockerContainerSensor(api, thread, variable) for variable in monitored_conditions if variable in _CONTAINER_MON_COND]

    if sensors:
        def monitor_stop(_service_or_event):
            """Stop the monitor thread."""
            _LOGGER.info("Stopping threads for Docker monitor")
            for t in threads.values():
                t.stop()

        add_entities(sensors, True)
        hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, monitor_stop)

def dockerVersion(api):
    raw_stats = api.version()
    return {
        'version'       : raw_stats.get('Version'   , None),
        'api_version'   : raw_stats.get('ApiVersion', None),
        'os'            : raw_stats.get('Os'        , None),
        'arch'          : raw_stats.get('Arch'      , None),
    }

class DockerContainerApi(threading.Thread):

    def __init__(self, container_name, api):
        self._container_name    = container_name
        self._api               = api

        self._container = self._api.containers.get(self._container_name)
        super(DockerContainerApi, self).__init__()

        self._stopper = threading.Event()
        self._stats = {}
        self._stats_stream = self._container.stats(stream=True, decode=True)

        _LOGGER.debug("Create thread for container {}".format(self._container.name))

    def run(self):
        for i in self._stats_stream:
            self._setStats(i)
            time.sleep(0.5)
            if self.stopped():
                break

    def stats(self):
        """Stats getter."""
        return self._stats

    def getContainerName(self):
        """Container name getter."""
        return self._container_name

    def stop(self, timeout=None):
        """Stop the thread."""
        _LOGGER.debug("Close thread for container {}".format(self._container.name))
        self._stopper.set()

    def stopped(self):
        """Return True is the thread is stopped."""
        return self._stopper.isSet()

    def _setStats(self, raw_stats):
        from dateutil import parser

        stats                   = {}
        stats['id']             = self._container.id
        stats['image']          = self._container.image.tags
        stats['status']         = self._container.attrs['State']['Status']

        stats['created']        = dt_util.as_local(parser.parse(self._container.attrs['Created'])).isoformat()
        stats['started']        = dt_util.as_local(parser.parse(self._container.attrs['State']['StartedAt'])).isoformat()

        if stats['status'] in ('running', 'paused'):
            stats['cpu']            = self._get_docker_cpu(raw_stats)
            stats['memory']         = self._get_docker_memory(raw_stats)
        else:
            stats['cpu']            = {}
            stats['memory']         = {}

        self._stats = stats

    def _get_docker_cpu(self, raw_stats):
        ret = {}
        cpu_new = {}

        try:
            cpu_new['total']    = raw_stats['cpu_stats']['cpu_usage']['total_usage']
            cpu_new['system']   = raw_stats['cpu_stats']['system_cpu_usage']

            if 'online_cpus' in raw_stats['cpu_stats']:
                ret['online_cpus'] = raw_stats['cpu_stats']['online_cpus']
            else:
                ret['online_cpus'] = len(raw_stats['cpu_stats']['cpu_usage']['percpu_usage'] or [])
        except KeyError as e:
            # raw_stats do not have CPU information
            _LOGGER.info("Cannot grab CPU usage for container {} ({})".format(self._container.id, e))
            _LOGGER.debug(raw_stats)
        else:
            if not hasattr(self, 'cpu_old'):
                # First call, we init the cpu_old variable
                try:
                    self.cpu_old = cpu_new
                except (IOError, UnboundLocalError):
                    pass

            cpu_delta       = float(cpu_new['total']  - self.cpu_old['total'])
            system_delta    = float(cpu_new['system'] - self.cpu_old['system'])
            if cpu_delta > 0.0 and system_delta > 0.0:
                ret['total'] = round((cpu_delta / system_delta) * float(ret['online_cpus']) * 100.0, PRECISION)
            else:
                ret['total'] = round(0.0, PRECISION)

            self.cpu_old = cpu_new

        return ret

    def _get_docker_memory(self, raw_stats):
        ret = {}

        try:
            ret['usage'] = raw_stats['memory_stats']['usage']
            ret['limit'] = raw_stats['memory_stats']['limit']
            ret['max_usage'] = raw_stats['memory_stats']['max_usage']
        except (KeyError, TypeError) as e:
            # raw_stats do not have MEM information
            _LOGGER.info("Cannot grab MEM usage for container {} ({})".format(self._container.id, e))
            _LOGGER.debug(raw_stats)
        else:
            ret['usage_percent'] = round(float(ret['usage']) / float(ret['limit']) * 100.0, PRECISION)

        return ret

class DockerUtilSensor(Entity):
    """Representation of a Docker Sensor."""

    def __init__(self, api, variable):
        """Initialize the sensor."""
        self._api           = api

        self._var_id        = variable
        self._var_name      = _UTILISATION_MON_COND[variable][0]
        self._var_unit      = _UTILISATION_MON_COND[variable][1]
        self._var_icon      = _UTILISATION_MON_COND[variable][2]

        self._state         = None
        self._attributes    = {
            ATTR_ATTRIBUTION:   CONF_ATTRIBUTION
        }

        _LOGGER.info("Initializing utilization sensor \"{}\"".format(self._var_id))

    @property
    def name(self):
        """Return the name of the sensor, if any."""
        return "Docker {}".format(self._var_name)

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
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
            version = dockerVersion(self._api)
            self._state                         = version.get('version', None)
            self._attributes[ATTR_VERSION_API]  = version.get('api_version', None)
            self._attributes[ATTR_VERSION_OS]   = version.get('os', None)
            self._attributes[ATTR_VERSION_ARCH] = version.get('arch', None)

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

class DockerContainerSensor(Entity):
    """Representation of a Docker Sensor."""

    def __init__(self, api, container_thread, variable):
        """Initialize the sensor."""
        self._api           = api
        self._thread        = container_thread

        self._var_id        = variable
        self._var_name      = _CONTAINER_MON_COND[variable][0]
        self._var_unit      = _CONTAINER_MON_COND[variable][1]
        self._var_icon      = _CONTAINER_MON_COND[variable][2]

        self._state         = None
        self._attributes    = {
            ATTR_ATTRIBUTION:   CONF_ATTRIBUTION
        }

        self._name          = self._thread.getContainerName()

        _LOGGER.info("Initializing Docker sensor \"{}\" with parameter: {}".format(self._name, self._var_name))

    @property
    def name(self):
        """Return the name of the sensor, if any."""
        return "Docker {} {}".format(self._name, self._var_name)

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
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
        stats = self._thread.stats()
        if self._var_id == CONTAINER_MONITOR_STATUS:
            self._state                         = stats.get('status', None)
        elif self._var_id == CONTAINER_MONITOR_CPU_PERCENTAGE:
            self._state                         = stats.get('cpu', {}).get('total')
        elif self._var_id == CONTAINER_MONITOR_MEMORY_USAGE:
            use  = stats.get('memory', {}).get('usage')
            if use is not None:
                self._state = round(use / (1024 ** 2)) # Bytes to MB
            else:
                self._state = None
        elif self._var_id == CONTAINER_MONITOR_MEMORY_PERCENTAGE:
            self._state                         = stats.get('memory', {}).get('usage_percent')

        if self._var_id in (CONTAINER_MONITOR_CPU_PERCENTAGE):
            cpus = stats.get('cpu', {}).get('online_cpus')
            if cpus is not None:
                self._attributes[ATTR_ONLINE_CPUS]      = cpus
        elif self._var_id in (CONTAINER_MONITOR_MEMORY_USAGE, CONTAINER_MONITOR_MEMORY_PERCENTAGE):
            limit = stats.get('memory', {}).get('limit')
            if limit is not None:
                self._attributes[ATTR_MEMORY_LIMIT]     = str(round(limit / (1024 ** 2))) + ' MB'

        self._attributes[ATTR_CREATED]      = stats.get('created', None)
        self._attributes[ATTR_STARTED_AT]   = stats.get('started', None)

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return self._attributes