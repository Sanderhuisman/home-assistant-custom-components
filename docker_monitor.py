'''
Docker Monitor component

For more details about this component, please refer to the documentation at
https://github.com/Sanderhuisman/home-assistant-custom-components
'''
import logging
import threading
import time
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    CONF_MONITORED_CONDITIONS,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    EVENT_HOMEASSISTANT_STOP
)
from homeassistant.core import callback
from homeassistant.helpers.discovery import load_platform

REQUIREMENTS = ['docker==3.7.0', 'python-dateutil==2.7.5']

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'docker_monitor'

CONF_ATTRIBUTION = 'Data provided by Docker'

DOCKER_HANDLE = 'docker_handle'
DATA_DOCKER_API = 'api'
DATA_CONFIG = 'config'

PRECISION = 2

DEFAULT_URL = 'unix://var/run/docker.sock'

DEFAULT_SCAN_INTERVAL = timedelta(seconds=10)

DOCKER_TYPE = [
    'sensor',
    'switch'
]

CONF_CONTAINERS = 'containers'

UTILISATION_MONITOR_VERSION = 'utilization_version'

CONTAINER_MONITOR_STATUS = 'container_status'
CONTAINER_MONITOR_UPTIME = 'container_uptime'
CONTAINER_MONITOR_IMAGE = 'container_image'
CONTAINER_MONITOR_MEMORY_USAGE = 'container_memory_usage'
CONTAINER_MONITOR_MEMORY_PERCENTAGE = 'container_memory_percentage_usage'
CONTAINER_MONITOR_CPU_PERCENTAGE = 'container_cpu_percentage_usage'
CONTAINER_MONITOR_NETWORK_UP = 'container_network_up'
CONTAINER_MONITOR_NETWORK_DOWN = 'container_network_down'

_UTILISATION_MON_COND = {
    UTILISATION_MONITOR_VERSION: ['Version', None, 'mdi:information-outline', None],
}

_CONTAINER_MON_COND = {
    CONTAINER_MONITOR_STATUS: ['Status', None, 'mdi:checkbox-marked-circle-outline', None],
    CONTAINER_MONITOR_UPTIME: ['Up Time', '', 'mdi:clock', 'timestamp'],
    CONTAINER_MONITOR_IMAGE: ['Image', None, 'mdi:information-outline', None],
    CONTAINER_MONITOR_MEMORY_USAGE: ['Memory use', 'MB', 'mdi:memory', None],
    CONTAINER_MONITOR_MEMORY_PERCENTAGE: ['Memory use (percent)', '%', 'mdi:memory', None],
    CONTAINER_MONITOR_CPU_PERCENTAGE: ['CPU use', '%', 'mdi:chip', None],
    CONTAINER_MONITOR_NETWORK_UP: ['Network Up', 'MB', 'mdi:upload', None],
    CONTAINER_MONITOR_NETWORK_DOWN: ['Network Down', 'MB', 'mdi:download', None],
}

_MONITORED_CONDITIONS = \
    list(_UTILISATION_MON_COND.keys()) + \
    list(_CONTAINER_MON_COND.keys())

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Optional(CONF_URL, default=DEFAULT_URL):
            cv.string,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL):
            cv.time_period,
        vol.Optional(CONF_MONITORED_CONDITIONS, default=_MONITORED_CONDITIONS):
            vol.All(cv.ensure_list, [vol.In(_MONITORED_CONDITIONS)]),
        vol.Optional(CONF_CONTAINERS):
            cv.ensure_list,
    })
}, extra=vol.ALLOW_EXTRA)


def setup(hass, config):
    _LOGGER.info("Settings: {}".format(config[DOMAIN]))

    host = config[DOMAIN].get(CONF_URL)

    try:
        api = DockerAPI(host)
    except (ImportError, ConnectionError) as e:
        _LOGGER.info("Error setting up Docker API ({})".format(e))
        return False
    else:
        version = api.get_info()
        _LOGGER.debug("Docker version: {}".format(
            version.get('version', None)))

        hass.data[DOCKER_HANDLE] = {}
        hass.data[DOCKER_HANDLE][DATA_DOCKER_API] = api
        hass.data[DOCKER_HANDLE][DATA_CONFIG] = {
            CONF_CONTAINERS: config[DOMAIN].get(CONF_CONTAINERS, [container.get_name() for container in api.get_containers()]),
            CONF_MONITORED_CONDITIONS: config[DOMAIN].get(CONF_MONITORED_CONDITIONS),
            CONF_SCAN_INTERVAL: config[DOMAIN].get(CONF_SCAN_INTERVAL),
        }

        for component in DOCKER_TYPE:
            load_platform(hass, component, DOMAIN, {}, config)

        def monitor_stop(_service_or_event):
            """Stop the monitor thread."""
            _LOGGER.info("Stopping threads for Docker monitor")
            api.exit()

        hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, monitor_stop)

        return True


""" 
Docker API abstraction 
"""


class DockerAPI:
    def __init__(self, base_url):
        self._base_url = base_url
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
            self._containers[container.name] = DockerContainerAPI(
                self._client, container.name)

    def exit(self):
        _LOGGER.info("Stopping threads for Docker monitor")
        for container in self._containers.values():
            container.exit()

    def get_info(self):
        version = {}
        try:
            raw_stats = self._client.version()
            version = {
                'version': raw_stats.get('Version', None),
                'api_version': raw_stats.get('ApiVersion', None),
                'os': raw_stats.get('Os', None),
                'arch': raw_stats.get('Arch', None),
                'kernel': raw_stats.get('KernelVersion', None),
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
        self._client = client
        self._name = name

        self._subscribers = []

        self._container = client.containers.get(self._name)

        self._thread = None
        self._stopper = None

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
            self._stopper = threading.Event()
            thread = threading.Thread(target=self._runnable, kwargs={
                                      'interval': interval})
            self._thread = thread
            thread.start()

        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def get_info(self):
        from dateutil import parser

        self._container.reload()
        info = {
            'id': self._container.id,
            'image': self._container.image.tags,
            'status': self._container.attrs['State']['Status'],
            'created': parser.parse(self._container.attrs['Created']),
            'started': parser.parse(self._container.attrs['State']['StartedAt']),
        }

        return info

    def start(self):
        _LOGGER.info("Start container {}".format(self._name))
        self._container.start()

    def stop(self, timeout=10):
        _LOGGER.info("Stop container {}".format(self._name))
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
                    cpu_new['total'] = raw['cpu_stats']['cpu_usage']['total_usage']
                    cpu_new['system'] = raw['cpu_stats']['system_cpu_usage']

                    # Compatibility wih older Docker API
                    if 'online_cpus' in raw['cpu_stats']:
                        cpu_stats['online_cpus'] = raw['cpu_stats']['online_cpus']
                    else:
                        cpu_stats['online_cpus'] = len(
                            raw['cpu_stats']['cpu_usage']['percpu_usage'] or [])
                except KeyError as e:
                    # raw do not have CPU information
                    _LOGGER.info("Cannot grab CPU usage for container {} ({})".format(
                        self._container.id, e))
                    _LOGGER.debug(raw)
                else:
                    if cpu_old:
                        cpu_delta = float(cpu_new['total'] - cpu_old['total'])
                        system_delta = float(
                            cpu_new['system'] - cpu_old['system'])

                        cpu_stats['total'] = round(0.0, PRECISION)
                        if cpu_delta > 0.0 and system_delta > 0.0:
                            cpu_stats['total'] = round(
                                (cpu_delta / system_delta) * float(cpu_stats['online_cpus']) * 100.0, PRECISION)

                    cpu_old = cpu_new

                memory_stats = {}
                try:
                    memory_stats['usage'] = raw['memory_stats']['usage']
                    memory_stats['limit'] = raw['memory_stats']['limit']
                    memory_stats['max_usage'] = raw['memory_stats']['max_usage']
                except (KeyError, TypeError) as e:
                    # raw_stats do not have MEM information
                    _LOGGER.info("Cannot grab MEM usage for container {} ({})".format(
                        self._container.id, e))
                    _LOGGER.debug(raw)
                else:
                    memory_stats['usage_percent'] = round(
                        float(memory_stats['usage']) / float(memory_stats['limit']) * 100.0, PRECISION)

                network_stats = {}
                try:

                    _LOGGER.debug("Found network stats: {}".format(raw["networks"]))

                    netstats = raw["networks"]['eth0']
                    network_stats['total_rx'] = netstats['rx_bytes']
                    network_stats['total_tx'] = netstats['tx_bytes']
                except KeyError as e:
                    # raw_stats do not have NETWORK information
                    _LOGGER.info("Cannot grab NET usage for container {} ({})".format(
                        self._container.id, e))
                    _LOGGER.debug(raw)

                stats['cpu'] = cpu_stats
                stats['memory'] = memory_stats
                stats['network'] = network_stats
            else:
                stats['cpu'] = {}
                stats['memory'] = {}
                stats['network'] = {}

            self._notify(stats)
            time.sleep(interval)
