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
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import callback
from homeassistant.helpers import discovery
from homeassistant.util import slugify as util_slugify

from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    CONF_ATTRIBUTION,
    PLATFORMS,
    DOCKER_HANDLE,
    DATA_DOCKER_API,
    DATA_CONFIG,
    DEFAULT_URL,
    DEFAULT_NAME,
    CONF_EVENTS,
    CONF_CONTAINERS,
    CONF_MONITOR_UTILISATION_VERSION,
    CONF_MONITOR_CONTAINER_STATUS,
    CONF_MONITOR_CONTAINER_UPTIME,
    CONF_MONITOR_CONTAINER_IMAGE,
    CONF_MONITOR_CONTAINER_CPU_PERCENTAGE,
    CONF_MONITOR_CONTAINER_MEMORY_USAGE,
    CONF_MONITOR_CONTAINER_MEMORY_PERCENTAGE,
    CONF_MONITOR_CONTAINER_NETWORK_SPEED_UP,
    CONF_MONITOR_CONTAINER_NETWORK_SPEED_DOWN,
    CONF_MONITOR_CONTAINER_NETWORK_TOTAL_UP,
    CONF_MONITOR_CONTAINER_NETWORK_TOTAL_DOWN,
    CONF_MONITOR_UTILISATION_CONDITIONS,
    CONF_MONITOR_CONTAINER_CONDITIONS,
    EVENT_CONTAINER,
    PRECISION,
    CONTAINER_INFO,
    CONTAINER_INFO_ID,
    CONTAINER_INFO_IMAGE,
    CONTAINER_INFO_STATUS,
    CONTAINER_INFO_CREATED,
    CONTAINER_INFO_STARTED,
    VERSION_INFO_VERSION,
    VERSION_INFO_API_VERSION,
    VERSION_INFO_OS,
    VERSION_INFO_ARCHITECTURE,
    VERSION_INFO_KERNEL,
    EVENT_INFO_CONTAINER,
    EVENT_INFO_IMAGE,
    EVENT_INFO_STATUS,
    EVENT_INFO_ID,
)

VERSION = '0.0.2'

REQUIREMENTS = ['docker==3.7.0', 'python-dateutil==2.7.5']

_LOGGER = logging.getLogger(__name__)

MONITORED_CONDITIONS = \
    list(CONF_MONITOR_UTILISATION_CONDITIONS.keys()) + \
    list(CONF_MONITOR_CONTAINER_CONDITIONS.keys())

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Optional(CONF_NAME, default=DEFAULT_NAME):
            cv.string,
        vol.Optional(CONF_URL, default=DEFAULT_URL):
            cv.string,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL):
            cv.time_period,
        vol.Optional(CONF_EVENTS, default=False):
            cv.boolean,
        vol.Optional(CONF_MONITORED_CONDITIONS, default=MONITORED_CONDITIONS):
            vol.All(cv.ensure_list, [vol.In(MONITORED_CONDITIONS)]),
        vol.Optional(CONF_CONTAINERS):
            cv.ensure_list,
    })
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass, config):
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
            version.get(VERSION_INFO_VERSION, None)))

        hass.data[DOCKER_HANDLE] = {}
        hass.data[DOCKER_HANDLE][DATA_DOCKER_API] = api
        hass.data[DOCKER_HANDLE][DATA_CONFIG] = {
            CONF_NAME: config[DOMAIN][CONF_NAME],
            CONF_CONTAINERS: config[DOMAIN].get(CONF_CONTAINERS, [container.get_name() for container in api.get_containers()]),
            CONF_MONITORED_CONDITIONS: config[DOMAIN].get(CONF_MONITORED_CONDITIONS),
            CONF_SCAN_INTERVAL: config[DOMAIN].get(CONF_SCAN_INTERVAL),
        }

        for platform in PLATFORMS:
            hass.async_create_task(
                discovery.async_load_platform(
                    hass, platform, DOMAIN, {}, config
                )
            )
            # load_platform(hass, platform, DOMAIN, {}, config)

        def monitor_stop(_service_or_event):
            """Stop the monitor thread."""
            _LOGGER.info("Stopping threads for Docker monitor")
            api.exit()

        hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, monitor_stop)

        def event_listener(message):
            event = util_slugify("{} {}".format(config[DOMAIN][CONF_NAME], EVENT_CONTAINER))
            _LOGGER.debug("Sending event {} notification with message {}".format(event, message))
            hass.bus.fire(event, message)

        if config[DOMAIN][CONF_EVENTS]:
            api.events(event_listener)

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
        self._event_callback_listeners = []

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
        self._events.close()
        for container in self._containers.values():
            container.exit()

    def events(self, callback):
        if not self._event_callback_listeners:
            thread = threading.Thread(target=self._runnable, kwargs={})
            thread.start()

        if callback not in self._event_callback_listeners:
            self._event_callback_listeners.append(callback)

    def get_info(self):
        version = {}
        try:
            raw_stats = self._client.version()
            version = {
                VERSION_INFO_VERSION: raw_stats.get('Version', None),
                VERSION_INFO_API_VERSION: raw_stats.get('ApiVersion', None),
                VERSION_INFO_OS: raw_stats.get('Os', None),
                VERSION_INFO_ARCHITECTURE: raw_stats.get('Arch', None),
                VERSION_INFO_KERNEL: raw_stats.get('KernelVersion', None),
            }
        except Exception as e:
            _LOGGER.error("Cannot get Docker version ({})".format(e))

        return version

    def _runnable(self):
        self._events = self._client.events(decode=True)
        for event in self._events:
            _LOGGER.debug("Event: ({})".format(event))
            try:
                # Only interested in container events
                if event['Type'] == 'container':
                    message = {
                        EVENT_INFO_CONTAINER: event['Actor']['Attributes'].get('name'),
                        EVENT_INFO_IMAGE: event['from'],
                        EVENT_INFO_STATUS: event['status'],
                        EVENT_INFO_ID: event['id'],
                    }
                    _LOGGER.info("Container event: ({})".format(message))

                    for callback in self._event_callback_listeners:
                        callback(message)
            except KeyError as e:
                _LOGGER.error("Key error: ({})".format(e))
                pass

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
            CONTAINER_INFO_ID: self._container.id,
            CONTAINER_INFO_IMAGE: self._container.image.tags,
            CONTAINER_INFO_STATUS: self._container.attrs['State']['Status'],
            CONTAINER_INFO_CREATED: parser.parse(self._container.attrs['Created']),
            CONTAINER_INFO_STARTED: parser.parse(self._container.attrs['State']['StartedAt']),
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
        from dateutil import parser

        stream = self._container.stats(stream=True, decode=True)

        cpu_old = {}
        network_old = {}
        for raw in stream:
            if self._stopper.isSet():
                break

            stats = {}

            stats[CONTAINER_INFO] = self.get_info()
            if stats[CONTAINER_INFO][CONTAINER_INFO_STATUS] in ('running', 'paused'):
                stats['read'] = parser.parse(raw['read'])

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
                    network_new = {}
                    _LOGGER.debug("Found network stats: {}".format(raw["networks"]))
                    network_stats['total_tx'] = 0
                    network_stats['total_rx'] = 0
                    for if_name, data in raw["networks"].items():
                        _LOGGER.debug("Stats for interface {} -> up {} / down {}".format(
                            if_name, data["tx_bytes"], data["rx_bytes"]))
                        network_stats['total_tx'] += data["tx_bytes"]
                        network_stats['total_rx'] += data["rx_bytes"]

                    network_new = {
                        'read': stats['read'],
                        'total_tx': network_stats['total_tx'],
                        'total_rx': network_stats['total_rx'],
                    }

                except KeyError as e:
                    # raw_stats do not have NETWORK information
                    _LOGGER.info("Cannot grab NET usage for container {} ({})".format(
                        self._container.id, e))
                    _LOGGER.debug(raw)
                else:
                    if network_old:
                        tx = network_new['total_tx'] - network_old['total_tx']
                        rx = network_new['total_rx'] - network_old['total_rx']
                        tim = (network_new['read'] - network_old['read']).total_seconds()

                        network_stats['speed_tx'] = round(float(tx) / tim, PRECISION)
                        network_stats['speed_rx'] = round(float(rx) / tim, PRECISION)

                    network_old = network_new

                stats['cpu'] = cpu_stats
                stats['memory'] = memory_stats
                stats['network'] = network_stats
            else:
                stats['cpu'] = {}
                stats['memory'] = {}
                stats['network'] = {}

            self._notify(stats)
            time.sleep(interval)
