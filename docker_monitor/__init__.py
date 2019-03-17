'''
Docker Monitor component

For more details about this component, please refer to the documentation at
https://github.com/Sanderhuisman/home-assistant-custom-components
'''
import logging
import threading
import time

from homeassistant.helpers import config_validation as cv
import voluptuous as vol
from homeassistant.const import (
    CONF_HOSTS,
    ATTR_ATTRIBUTION,
    CONF_MONITORED_CONDITIONS,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    EVENT_HOMEASSISTANT_STOP,
    CONF_SENSORS,
)
from homeassistant.helpers.discovery import load_platform
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
    UPDATE_TOPIC,
)

VERSION = '0.0.2'

REQUIREMENTS = ['docker==3.7.0', 'python-dateutil==2.7.5']

_LOGGER = logging.getLogger(__name__)

CONF_MONITOR_UTILISATION_CONDITIONS_KEYS = list(CONF_MONITOR_UTILISATION_CONDITIONS.keys())
CONF_MONITOR_CONTAINER_CONDITIONS_KEYS = list(CONF_MONITOR_CONTAINER_CONDITIONS.keys())

CONTAINER_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME):
        cv.string,
    vol.Optional(CONF_SENSORS, default=CONF_MONITOR_CONTAINER_CONDITIONS_KEYS):
        vol.All(cv.ensure_list, [vol.In(CONF_MONITOR_CONTAINER_CONDITIONS_KEYS)]),
})

SERVER_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME, default=DEFAULT_NAME):
        cv.string,
    vol.Required(CONF_URL):
        cv.string,
    vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL):
        cv.time_period,
    vol.Optional(CONF_EVENTS, default=False):
        cv.boolean,
    vol.Optional(CONF_MONITORED_CONDITIONS, default=CONF_MONITOR_UTILISATION_CONDITIONS_KEYS):
        vol.All(cv.ensure_list, [vol.In(CONF_MONITOR_UTILISATION_CONDITIONS_KEYS)]),
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
                    _LOGGER.info("Sending event {} notification with message {}".format(event, message))
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

            def stats_listener():
                hass.helpers.dispatcher.dispatcher_send("{}_{}".format(UPDATE_TOPIC, util_slugify(name)))
            api.stats_listener.start_listen(stats_listener)

    def monitor_stop(_service_or_event):
        """Stop the monitor threads."""
        _LOGGER.info("Stopping threads for Docker monitor")
        for api in hass.data[DOMAIN].values():
            api.exit()

    hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, monitor_stop)

    return True

class DockerMonitorApi:
    def __init__(self, base_url, event_callback=None):
        self._base_url = base_url

        try:
            import docker
        except ImportError as e:
            _LOGGER.error("Missing Docker library ({})".format(e))
            raise ImportError()

        try:
            self._client = docker.DockerClient(base_url=self._base_url)
        except Exception as e:
            _LOGGER.error("Can not connect to Docker ({})".format(e))
            raise ConnectionError()

        self.containers = {}
        for container in self._client.containers.list(all=True) or []:
            self.containers[container.name] = ContainerData(container)

        self.stats_listener = DockerContainerStats(self._client, self)

        self._event_listener = None
        if event_callback:
            def api_event_callback(message):
                event_callback(message)
            self._event_listener = DockerContainerEventListener(self._client, api_event_callback)
            self._event_listener.start()

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

    def get_containers(self):
        return self.containers

    def exit(self):
        if self._event_listener:
            self._event_listener.shutdown()
        if self.stats_listener.isAlive():
            self.stats_listener.shutdown()

class DockerContainerEventListener(threading.Thread):
    """Docker monitor container event listener thread."""

    def __init__(self, client, callback):
        super().__init__(name='DockerContainerEventListener')

        self._client = client
        self._callback = callback

        self._event_stream = None

    def shutdown(self):
        """Signal shutdown of processing event."""
        if self._event_stream:
            self._event_stream.close()
        self.join()

        _LOGGER.debug("Event listener thread stopped")

    def run(self):
        self._event_stream = self._client.events(decode=True)
        for event in self._event_stream:
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

                    self.__notify(message)
            except KeyError as e:
                _LOGGER.error("Key error: ({})".format(e))
                pass

    def __notify(self, message):
        if self._callback:
            self._callback(message)

class ContainerData:
    def __init__(self, container):
        self._container = container

        self._name = container.name
        self._stats = None

    def get_name(self):
        return self._name

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

    def get_stats(self):
        return self._stats

    def set_stats(self, stats):
        self._stats = stats


class DockerContainerStats(threading.Thread):
    """Docker monitor container stats listener thread."""

    def __init__(self, client, api):
        super().__init__(name='DockerContainerStats')

        self._client = client
        self._api = api

        self._stopper = threading.Event()
        self._callback = None
        self._interval = None
        self._old = {}

    def start_listen(self, callback, interval=10):
        """Start event-processing thread."""
        _LOGGER.debug("Start Stats listener thread")
        self._callback = callback
        self._interval = interval
        self.start()

    def shutdown(self):
        """Signal shutdown of processing event."""
        self._stopper.set()
        self.join()
        _LOGGER.debug("Stats listener thread stopped")

    def run(self):
        streams = {}
        while not self._stopper.isSet():
            for name, container in self._api.get_containers().items():
                status = container.get_info()[CONTAINER_INFO_STATUS]

                stats = None
                if status in ('running', 'paused'):
                    if name not in streams:
                        streams[name] = self._client.containers.get(name).stats(stream=True, decode=True)

                    for raw in streams[name]:
                        stats = self.__parse_stats(name, raw)

                        # Break from event to streams other streams
                        break
                elif name in streams:
                    streams[name].close()

                    # Remove old stats from this container
                    if name in self._old:
                        self._old.pop(name)

                container.set_stats(stats)

            self._callback()

            # Wait before read
            self._stopper.wait(self._interval)

        # Cleanup
        for stream in streams.values():
            stream.close()

    def __parse_stats(self, name, raw):
        from dateutil import parser

        stats = {}
        stats['read'] = parser.parse(raw['read'])

        old = self._old.get(name, {})

        # CPU stats
        cpu = {}
        try:
            cpu_new = {}
            cpu_new['total'] = raw['cpu_stats']['cpu_usage']['total_usage']
            cpu_new['system'] = raw['cpu_stats']['system_cpu_usage']

            # Compatibility wih older Docker API
            if 'online_cpus' in raw['cpu_stats']:
                cpu['online_cpus'] = raw['cpu_stats']['online_cpus']
            else:
                cpu['online_cpus'] = len(raw['cpu_stats']['cpu_usage']['percpu_usage'] or [])
        except KeyError as e:
            # raw do not have CPU information
            _LOGGER.info("Cannot grab CPU usage for container {} ({})".format(name, e))
            _LOGGER.debug(raw)
        else:
            if 'cpu' in old:
                cpu_delta = cpu_new['total'] - old['cpu']['total']
                system_delta = cpu_new['system'] - old['cpu']['system']

                cpu['total'] = 0.0
                if cpu_delta > 0 and system_delta > 0:
                    cpu['total'] = (float(cpu_delta) / float(system_delta)) * float(cpu['online_cpus']) * 100.0

            old['cpu'] = cpu_new

        # Memory stats
        memory = {}
        try:
            memory['usage'] = raw['memory_stats']['usage']
            memory['limit'] = raw['memory_stats']['limit']
            memory['max_usage'] = raw['memory_stats']['max_usage']
        except (KeyError, TypeError) as e:
            # raw_stats do not have memory information
            _LOGGER.info("Cannot grab memory usage for container {} ({})".format(name, e))
            _LOGGER.debug(raw)
        else:
            memory['usage_percent'] = float(memory['usage']) / float(memory['limit']) * 100.0

        # Network stats
        network = {}
        try:
            _LOGGER.debug("Found network stats: {}".format(raw["networks"]))
            network['total_tx'] = 0
            network['total_rx'] = 0
            for if_name, data in raw["networks"].items():
                _LOGGER.debug("Stats for interface {} -> up {} / down {}".format(if_name, data["tx_bytes"], data["rx_bytes"]))
                network['total_tx'] += data["tx_bytes"]
                network['total_rx'] += data["rx_bytes"]
        except KeyError as e:
            # raw_stats do not have network information
            _LOGGER.info("Cannot grab network usage for container {} ({})".format(name, e))
            _LOGGER.debug(raw)

        stats['cpu'] = cpu
        stats['memory'] = memory
        stats['network'] = network

        # Update stats history
        self._old[name] = old

        return stats
