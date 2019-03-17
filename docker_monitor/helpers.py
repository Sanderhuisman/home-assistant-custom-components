import logging
import threading

from .const import (
    CONTAINER_INFO,
    CONTAINER_INFO_CREATED,
    CONTAINER_INFO_ID,
    CONTAINER_INFO_IMAGE,
    CONTAINER_INFO_STARTED,
    CONTAINER_INFO_STATUS,
    EVENT_INFO_CONTAINER,
    EVENT_INFO_ID,
    EVENT_INFO_IMAGE,
    EVENT_INFO_STATUS,
    VERSION_INFO_API_VERSION,
    VERSION_INFO_ARCHITECTURE,
    VERSION_INFO_KERNEL,
    VERSION_INFO_OS,
    VERSION_INFO_VERSION
)

_LOGGER = logging.getLogger(__name__)


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

        self._stats_listener = DockerContainerStats(self._client, self)

        self._event_listener = None
        if event_callback:
            def api_event_callback(message):
                event_callback(message)
            self._event_listener = DockerContainerEventListener(
                self._client, api_event_callback)

    def start(self):
        if self._event_listener:
            self._event_listener.start()

        self._stats_listener.start_listen()

    def exit(self):
        if self._event_listener:
            self._event_listener.shutdown()
        if self._stats_listener.isAlive():
            self._stats_listener.shutdown()

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
        self._subscribers = []

    def get_name(self):
        return self._name

    def register_callback(self, callback):
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
        self._notify()

    def stop(self, timeout=10):
        _LOGGER.info("Stop container {}".format(self._name))
        self._container.stop(timeout=timeout)
        self._container.wait(timeout=timeout)
        self._notify()

    def get_stats(self):
        return self._stats

    def set_stats(self, stats):
        self._stats = stats
        self._notify()

    def _notify(self):
        for callback in self._subscribers:
            callback()


class DockerContainerStats(threading.Thread):
    """Docker monitor container stats listener thread."""

    def __init__(self, client, api):
        super().__init__(name='DockerContainerStats')

        self._client = client
        self._api = api

        self._stopper = threading.Event()
        self._interval = None
        self._old = {}

    def start_listen(self, interval=10):
        """Start event-processing thread."""
        _LOGGER.debug("Start Stats listener thread")
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
                        streams[name] = self._client.containers.get(
                            name).stats(stream=True, decode=True)

                    for raw in streams[name]:
                        stats = self.__parse_stats(name, raw)

                        # Break from event to streams other streams
                        break
                elif name in streams:
                    streams[name].close()
                    streams.pop(name)

                    # Remove old stats from this container
                    if name in self._old:
                        self._old.pop(name)

                container.set_stats(stats)

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
                cpu['online_cpus'] = len(
                    raw['cpu_stats']['cpu_usage']['percpu_usage'] or [])
        except KeyError as e:
            # raw do not have CPU information
            _LOGGER.info(
                "Cannot grab CPU usage for container {} ({})".format(name, e))
            _LOGGER.debug(raw)
        else:
            if 'cpu' in old:
                cpu_delta = cpu_new['total'] - old['cpu']['total']
                system_delta = cpu_new['system'] - old['cpu']['system']

                cpu['total'] = 0.0
                if cpu_delta > 0 and system_delta > 0:
                    cpu['total'] = (
                        float(cpu_delta) / float(system_delta)) * float(cpu['online_cpus']) * 100.0

            old['cpu'] = cpu_new

        # Memory stats
        memory = {}
        try:
            memory['usage'] = raw['memory_stats']['usage']
            memory['limit'] = raw['memory_stats']['limit']
            memory['max_usage'] = raw['memory_stats']['max_usage']
        except (KeyError, TypeError) as e:
            # raw_stats do not have memory information
            _LOGGER.info(
                "Cannot grab memory usage for container {} ({})".format(name, e))
            _LOGGER.debug(raw)
        else:
            memory['usage_percent'] = float(
                memory['usage']) / float(memory['limit']) * 100.0

        # Network stats
        network = {}
        try:
            _LOGGER.debug("Found network stats: {}".format(raw["networks"]))
            network['total_tx'] = 0
            network['total_rx'] = 0
            for if_name, data in raw["networks"].items():
                _LOGGER.debug("Stats for interface {} -> up {} / down {}".format(
                    if_name, data["tx_bytes"], data["rx_bytes"]))
                network['total_tx'] += data["tx_bytes"]
                network['total_rx'] += data["rx_bytes"]
        except KeyError as e:
            # raw_stats do not have network information
            _LOGGER.info(
                "Cannot grab network usage for container {} ({})".format(name, e))
            _LOGGER.debug(raw)

        stats['cpu'] = cpu
        stats['memory'] = memory
        stats['network'] = network

        # Update stats history
        self._old[name] = old

        return stats
