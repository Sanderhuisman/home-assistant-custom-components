'''
Docker Monitor component

For more details about this component, please refer to the documentation at
https://github.com/Sanderhuisman/home-assistant-custom-components
'''
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
    CONF_SCAN_INTERVAL,
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

DEFAULT_SCAN_INTERVAL = timedelta(seconds=10)

UTILISATION_MONITOR_VERSION         = 'utilization_version'

CONTAINER_MONITOR_STATUS            = 'container_status'
CONTAINER_MONITOR_MEMORY_USAGE      = 'container_memory_usage'
CONTAINER_MONITOR_MEMORY_PERCENTAGE = 'container_memory_percentage_usage'
CONTAINER_MONITOR_CPU_PERCENTAGE    = 'container_cpu_percentage_usage'
CONTAINER_MONITOR_NETWORK_UP        = 'container_network_up'
CONTAINER_MONITOR_NETWORK_DOWN      = 'container_network_down'

_UTILISATION_MON_COND = {
    UTILISATION_MONITOR_VERSION         : ['Version'                , None      , 'mdi:information-outline'],
}

_CONTAINER_MON_COND = {
    CONTAINER_MONITOR_STATUS            : ['Status'                 , None      , 'mdi:checkbox-marked-circle-outline'  ],
    CONTAINER_MONITOR_MEMORY_USAGE      : ['Memory use'             , 'MB'      , 'mdi:memory'                          ],
    CONTAINER_MONITOR_MEMORY_PERCENTAGE : ['Memory use (percent)'   , '%'       , 'mdi:memory'                          ],
    CONTAINER_MONITOR_CPU_PERCENTAGE    : ['CPU use'                , '%'       , 'mdi:chip'                            ],
    CONTAINER_MONITOR_NETWORK_UP        : ['Network Up'             , 'MB'      , 'mdi:upload'                          ],
    CONTAINER_MONITOR_NETWORK_DOWN      : ['Network Down'           , 'MB'      , 'mdi:download'                        ],
}

_MONITORED_CONDITIONS = list(_UTILISATION_MON_COND.keys()) + \
    list(_CONTAINER_MON_COND.keys())

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_HOST, default=DEFAULT_HOST): 
        cv.string,
    vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL):
        cv.time_period,
    vol.Optional(CONF_MONITORED_CONDITIONS): 
        vol.All(cv.ensure_list, [vol.In(_MONITORED_CONDITIONS)]),
    vol.Optional(CONF_CONTAINERS): 
        cv.ensure_list,
})

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Docker Monitor Sensor."""

    host                    = config.get(CONF_HOST)
    monitored_conditions    = config.get(CONF_MONITORED_CONDITIONS)
    interval                = config.get(CONF_SCAN_INTERVAL).total_seconds()

    try:
        api = DockerAPI(host)
    except (ImportError, ConnectionError) as e:
        _LOGGER.info("Error setting up Docker sensor ({})".format(e))
        return

    version = api.get_info()
    _LOGGER.info("Docker version: {}".format(version.get('version', None)))

    sensors = [DockerUtilSensor(api, variable, interval) for variable in monitored_conditions if variable in _UTILISATION_MON_COND]

    containers = api.get_containers()
    names = [x.get_name() for x in containers] 

    for name in config.get(CONF_CONTAINERS, names):
        sensors += [DockerContainerSensor(api, name, variable, interval) for variable in monitored_conditions if variable in _CONTAINER_MON_COND]

    if sensors:
        def monitor_stop(_service_or_event):
            """Stop the monitor thread."""
            _LOGGER.info("Stopping threads for Docker monitor")
            api.exit()

        add_entities(sensors, True)
        hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, monitor_stop)

class DockerUtilSensor(Entity):
    """Representation of a Docker Sensor."""

    def __init__(self, api, variable, interval):
        """Initialize the sensor."""
        self._api           = api
        self._interval      = interval # TODO implement

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

    def __init__(self, api, name, variable, interval):
        """Initialize the sensor."""
        self._api           = api
        self._name          = name
        self._interval      = interval

        self._var_id        = variable
        self._var_name      = _CONTAINER_MON_COND[variable][0]
        self._var_unit      = _CONTAINER_MON_COND[variable][1]
        self._var_icon      = _CONTAINER_MON_COND[variable][2]

        self._state         = None
        self._attributes    = {
            ATTR_ATTRIBUTION:   CONF_ATTRIBUTION
        }

        self._container     = api.get_container(name)

        _LOGGER.info("Initializing Docker sensor \"{}\" with parameter: {}".format(self._name, self._var_name))

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
                    state = round(use / (1024 ** 2)) # Bytes to MB
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
                    self._attributes[ATTR_ONLINE_CPUS]      = cpus
            elif self._var_id in (CONTAINER_MONITOR_MEMORY_USAGE, CONTAINER_MONITOR_MEMORY_PERCENTAGE):
                limit = stats.get('memory', {}).get('limit')
                if limit is not None:
                    self._attributes[ATTR_MEMORY_LIMIT]     = str(round(limit / (1024 ** 2))) + ' MB'

            self._attributes[ATTR_CREATED]      = dt_util.as_local(stats['info']['created']).isoformat()
            self._attributes[ATTR_STARTED_AT]   = dt_util.as_local(stats['info']['started']).isoformat()

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

""" 
Docker API abstraction 
"""
class DockerAPI: 
    def __init__(self, base_url):
        self._base_url  = base_url
        try:
            import docker
        except ImportError as e:
            _LOGGER.error("Missing Docker library ({})".format(e))
            raise ImportError()

        self._containers = {}

        try:
            self._client = docker.DockerClient(base_url=self._base_url)
        except Exception as e:
            _LOGGER.error("Can not connect to Docker ({})".format(e))
            raise ConnectionError()

        for container in self._client.containers.list(all=True) or []:
            _LOGGER.debug("Found container: {}".format(container.name))
            self._containers[container.name] = DockerContainerAPI(self._client, container.name)

    def exit(self):
        _LOGGER.info("Stopping threads for Docker monitor")
        for container in self._containers.values():
            container.exit()
        
    def get_info(self):
        version = {}
        try:
            raw_stats = self._client.version()
            version = {
                'version'       : raw_stats.get('Version'       , None),
                'api_version'   : raw_stats.get('ApiVersion'    , None),
                'os'            : raw_stats.get('Os'            , None),
                'arch'          : raw_stats.get('Arch'          , None),
                'kernel'        : raw_stats.get('KernelVersion' , None),
            }
        except Exception as e:
            _LOGGER.error("Cannot get Docker version ({})".format(e))

        return version

    def get_containers(self):
        return list(self._containers.values())

    def get_container(self, name):
        container = None
        if name in self._containers:
            container = self._containers[name]
        return container

class DockerContainerAPI:
    def __init__(self, client, name):
        self._client        = client
        self._name          = name

        self._subscribers   = []

        self._container     = client.containers.get(self._name)

        self._thread    = None
        self._stopper   = None
    
    def get_name(self):
        return self._name

    # Call from DockerAPI
    def exit(self, timeout=None):
        """Stop the thread."""
        _LOGGER.debug("Close stats thread for container {}".format(self._name))
        if self._thread is not None:
            self._stopper.set()

    def stats(self, callback, interval=10):
        if not self._subscribers:
            self._stopper   = threading.Event()
            thread = threading.Thread(target=self._runnable, kwargs={'interval': interval})
            self._thread    = thread
            thread.start()

        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def get_info(self):
        from dateutil import parser

        self._container.reload()
        info = {
            'id'        : self._container.id,
            'image'     : self._container.image.tags,
            'status'    : self._container.attrs['State']['Status'],
            'created'   : parser.parse(self._container.attrs['Created']),
            'started'   : parser.parse(self._container.attrs['State']['StartedAt']),
        }

        return info

    def start(self):
        _LOGGER.info("Start container {}".format(self._name))
        # TODO extra handling?
        self._container.start()


    def stop(self, timeout=10):
        _LOGGER.info("Stop container {}".format(self._name))
        # TODO extra handling?
        self._container.stop(timeout=timeout)


    def _notify(self, message):
        _LOGGER.debug("Send notify for container {}".format(self._name))
        for callback in self._subscribers:
            callback(message)

    def _runnable(self, interval):
        stream = self._container.stats(stream=True, decode=True)

        cpu_old = {}
        for raw in stream:
            if self._stopper.isSet():
                break

            stats = {}

            stats['info'] = self.get_info()
            if stats['info']['status'] in ('running', 'paused'):
                cpu_stats = {}
                try:
                    cpu_new = {}
                    cpu_new['total']            = raw['cpu_stats']['cpu_usage']['total_usage']
                    cpu_new['system']           = raw['cpu_stats']['system_cpu_usage']

                    cpu_stats['online_cpus']    = raw['cpu_stats']['online_cpus']
                except KeyError as e:
                    # raw do not have CPU information
                    _LOGGER.info("Cannot grab CPU usage for container {} ({})".format(self._container.id, e))
                    _LOGGER.debug(raw)
                else:
                    if cpu_old:
                        cpu_delta       = float(cpu_new['total']  - cpu_old['total'])
                        system_delta    = float(cpu_new['system'] - cpu_old['system'])

                        cpu_stats['total'] = round(0.0, PRECISION)
                        if cpu_delta > 0.0 and system_delta > 0.0:
                            cpu_stats['total'] = round((cpu_delta / system_delta) * float(cpu_stats['online_cpus']) * 100.0, PRECISION)

                    cpu_old = cpu_new

                memory_stats = {}
                try:
                    memory_stats['usage']       = raw['memory_stats']['usage']
                    memory_stats['limit']       = raw['memory_stats']['limit']
                    memory_stats['max_usage']   = raw['memory_stats']['max_usage']
                except (KeyError, TypeError) as e:
                    # raw_stats do not have MEM information
                    _LOGGER.info("Cannot grab MEM usage for container {} ({})".format(self._container.id, e))
                    _LOGGER.debug(raw)
                else:
                    memory_stats['usage_percent'] = round(float(memory_stats['usage']) / float(memory_stats['limit']) * 100.0, PRECISION)

                network_stats = {}
                try:
                    netstats = raw["networks"]['eth0']
                    network_stats['total_rx'] = netstats['rx_bytes']
                    network_stats['total_tx'] = netstats['tx_bytes']
                except KeyError as e:
                    # raw_stats do not have NETWORK information
                    _LOGGER.info("Cannot grab NET usage for container {} ({})".format(self._container.id, e))
                    _LOGGER.debug(raw)

                stats['cpu']        = cpu_stats
                stats['memory']     = memory_stats
                stats['network']    = network_stats
            else:
                stats['cpu']        = {}
                stats['memory']     = {}
                stats['network']    = {}

            self._notify(stats)
            time.sleep(interval)
