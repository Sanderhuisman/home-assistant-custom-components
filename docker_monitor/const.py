"""Define constants for the Docker Monitor component."""
from datetime import timedelta

DOMAIN = 'docker_monitor'
PLATFORMS = [
    'sensor',
    'switch'
]
EVENT_CONTAINER = 'container_event'

DOCKER_HANDLE = 'docker_handle'
DATA_DOCKER_API = 'api'
DATA_CONFIG = 'config'

DEFAULT_SCAN_INTERVAL = timedelta(seconds=10)
DEFAULT_URL = 'unix://var/run/docker.sock'
DEFAULT_NAME = 'Docker'

CONF_EVENTS = 'events'
CONF_CONTAINERS = 'containers'

CONF_MONITOR_UTILISATION_VERSION = 'utilization_version'
CONF_MONITOR_CONTAINER_STATUS = 'container_status'
CONF_MONITOR_CONTAINER_UPTIME = 'container_uptime'
CONF_MONITOR_CONTAINER_IMAGE = 'container_image'
CONF_MONITOR_CONTAINER_CPU_PERCENTAGE = 'container_cpu_percentage_usage'
CONF_MONITOR_CONTAINER_MEMORY_USAGE = 'container_memory_usage'
CONF_MONITOR_CONTAINER_MEMORY_PERCENTAGE = 'container_memory_percentage_usage'
CONF_MONITOR_CONTAINER_NETWORK_SPEED_UP = 'container_network_speed_up'
CONF_MONITOR_CONTAINER_NETWORK_SPEED_DOWN = 'container_network_speed_down'
CONF_MONITOR_CONTAINER_NETWORK_TOTAL_UP = 'container_network_total_up'
CONF_MONITOR_CONTAINER_NETWORK_TOTAL_DOWN = 'container_network_total_down'

CONF_MONITOR_UTILISATION_CONDITIONS = {
    CONF_MONITOR_UTILISATION_VERSION: ['Version', None, 'mdi:information-outline', None],
}

CONF_MONITOR_CONTAINER_CONDITIONS = {
    CONF_MONITOR_CONTAINER_STATUS: ['Status', None, 'mdi:checkbox-marked-circle-outline', None],
    CONF_MONITOR_CONTAINER_UPTIME: ['Up Time', '', 'mdi:clock', 'timestamp'],
    CONF_MONITOR_CONTAINER_IMAGE: ['Image', None, 'mdi:information-outline', None],
    CONF_MONITOR_CONTAINER_CPU_PERCENTAGE: ['CPU use', '%', 'mdi:chip', None],
    CONF_MONITOR_CONTAINER_MEMORY_USAGE: ['Memory use', 'MB', 'mdi:memory', None],
    CONF_MONITOR_CONTAINER_MEMORY_PERCENTAGE: ['Memory use (percent)', '%', 'mdi:memory', None],
    CONF_MONITOR_CONTAINER_NETWORK_SPEED_UP: ['Network speed Up', 'kB/s', 'mdi:upload', None],
    CONF_MONITOR_CONTAINER_NETWORK_SPEED_DOWN: ['Network speed Down', 'kB/s', 'mdi:download', None],
    CONF_MONITOR_CONTAINER_NETWORK_TOTAL_UP: ['Network total Up', 'MB', 'mdi:upload', None],
    CONF_MONITOR_CONTAINER_NETWORK_TOTAL_DOWN: ['Network total Down', 'MB', 'mdi:download', None],
}

ATTR_CREATED = 'Created'
ATTR_IMAGE = 'Image'
ATTR_MEMORY_LIMIT = 'Memory_limit'
ATTR_ONLINE_CPUS = 'Online_CPUs'
ATTR_STARTED_AT = 'Started_at'
ATTR_VERSION_API = 'Api_version'
ATTR_VERSION_ARCH = 'Architecture'
ATTR_VERSION_OS = 'Os'

CONF_ATTRIBUTION = 'Data provided by Docker'

VERSION_INFO = 'info'
VERSION_INFO_VERSION = 'version'
VERSION_INFO_API_VERSION = 'api_version'
VERSION_INFO_OS = 'os'
VERSION_INFO_ARCHITECTURE = 'arch'
VERSION_INFO_KERNEL = 'kernel'

CONTAINER_INFO = 'info'
CONTAINER_INFO_ID = 'id'
CONTAINER_INFO_IMAGE = 'image'
CONTAINER_INFO_STATUS = 'status'
CONTAINER_INFO_CREATED = 'created'
CONTAINER_INFO_STARTED = 'started'

EVENT_INFO_CONTAINER = 'Container'
EVENT_INFO_IMAGE = 'Image'
EVENT_INFO_STATUS = 'Status'
EVENT_INFO_ID = 'Id'

ICON_SWITCH = 'mdi:docker'

PRECISION = 2
