"""
Support for Luftdaten sensors.

For more details about this platform, please refer to the documentation at
https://github.com/Sanderhuisman/home-assistant-custom-components
"""
import logging
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
import requests
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_MONITORED_CONDITIONS,
    CONF_NAME,
    CONF_SHOW_ON_MAP,
    TEMP_CELSIUS
)
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle

VERSION = '0.0.1'

_LOGGER = logging.getLogger(__name__)

BASE_URL = 'https://api.luftdaten.info/v1'

ATTR_SENSOR_ID = 'sensor_id'

CONF_ATTRIBUTION = "Data provided by luftdaten.info"

VOLUME_MICROGRAMS_PER_CUBIC_METER = 'µg/m3'

SENSOR_TEMPERATURE = 'temperature'
SENSOR_HUMIDITY = 'humidity'
SENSOR_PM10 = 'P1'
SENSOR_PM2_5 = 'P2'
SENSOR_PRESSURE = 'pressure'

SENSOR_TYPES = {
    SENSOR_TEMPERATURE: ['Temperature', TEMP_CELSIUS, 'mdi:thermometer'],
    SENSOR_HUMIDITY: ['Humidity', '%', 'mdi:water-percent'],
    SENSOR_PRESSURE: ['Pressure', 'Pa', 'mdi:arrow-down-bold'],
    SENSOR_PM10: ['PM10', VOLUME_MICROGRAMS_PER_CUBIC_METER, 'mdi:thought-bubble'],
    SENSOR_PM2_5: ['PM2.5', VOLUME_MICROGRAMS_PER_CUBIC_METER,
                   'mdi:thought-bubble-outline']
}

DEFAULT_NAME = 'Luftdaten'

CONF_SENSORID = 'sensorid'

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=5)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_SENSORID): cv.positive_int,
    vol.Required(CONF_MONITORED_CONDITIONS):
        vol.All(cv.ensure_list, [vol.In(SENSOR_TYPES)]),
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
})


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Luftdaten sensor."""
    sensor_id = config.get(CONF_SENSORID)
    monitored_conditions = config.get(CONF_MONITORED_CONDITIONS)

    try:
        api = LuftdatenApi(sensor_id)
    except Exception as e:
        _LOGGER.error("Could not setup Lufdaten sensor ({})".format(e))
        return False
    else:
        if api.data is None:
            _LOGGER.error("Sensor is not available: {}".format(sensor_id))
            return

        sensors = [LuftdatenSensor(api, variable)
                   for variable in monitored_conditions
                   if variable in SENSOR_TYPES and variable in api.data]

        add_entities(sensors, True)

        return True


class LuftdatenApi:
    def __init__(self, sensor_id):
        self.sensor_id = sensor_id
        self.data = {
            'humidity': None,
            'P1': None,
            'P2': None,
            'pressure': None,
            'temperature': None,
        }

        self._get_data()

    def _get_data(self):
        response = requests.get(
            BASE_URL + '/sensor/{}/'.format(self.sensor_id))
        _LOGGER.info("Status code: {} with text: {}".format(
            response.status_code, response.text))
        if response.status_code == 200:
            data = response.json()

            if data is not None:
                # Get last measurement
                sensor_data = sorted(
                    data, key=lambda timestamp: timestamp['timestamp'], reverse=True)[0]

                for entry in sensor_data['sensordatavalues']:
                    self.data[entry['value_type']] = float(entry['value'])
            else:
                self.data = None
                return

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Update function for updating api information."""
        self._get_data()


class LuftdatenSensor(Entity):
    """Implementation of a Luftdaten sensor."""

    def __init__(self, api, sensor):
        pass
        """Initialize the Luftdaten sensor."""
        self._api = api
        self.sensor = sensor
        self._var_name = SENSOR_TYPES[sensor][0]
        self._var_units = SENSOR_TYPES[sensor][1]
        self._var_icon = SENSOR_TYPES[sensor][2]

        self._state = None
        self._attributes = {}
        self._attributes[ATTR_ATTRIBUTION] = CONF_ATTRIBUTION

    @property
    def name(self):
        """Return the name of the sensor, if any."""
        return "Luftdaten ({}) {}".format(self._api.sensor_id, self._var_name)

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
        """Return the unit of measurement of this entity, if any."""
        return self._var_units

    def update(self):
        """Get the latest data for the states."""
        self._api.update()

        self._state = self._api.data.get(self.sensor, None)

        self._attributes[ATTR_SENSOR_ID] = self._api.sensor_id

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return self._attributes
