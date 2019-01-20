"""
Support for Eetlijst Sensors.

For more details about this platform, please refer to the documentation at
https://github.com/Sanderhuisman/home-assistant-custom-components
"""
import logging
import re
import urllib.parse
from datetime import datetime, timedelta

import homeassistant.helpers.config_validation as cv
import pytz
import requests
import voluptuous as vol
from bs4 import BeautifulSoup
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    CONF_PASSWORD,
    CONF_USERNAME
)
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle

REQUIREMENTS = ['beautifulsoup4==4.7.0']

_LOGGER = logging.getLogger(__name__)

CONF_ATTRIBUTION = 'Data provided by Eetlijst'

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=5)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
})

BASE_URL = "http://www.eetlijst.nl/"

RE_DIGIT = re.compile(r"\d+")
RE_JAVASCRIPT_VS_1 = re.compile(r"javascript:vs")
RE_JAVASCRIPT_VS_2 = re.compile(r"javascript:vs\(([0-9]*)\);")
RE_JAVASCRIPT_K = re.compile(r"javascript:k\(([0-9]*),([-0-9]*),([-0-9]*)\);")
RE_RESIDENTS = re.compile(r"Meer informatie over")
RE_LAST_CHANGED = re.compile(r"onveranderd sinds ([0-9]+):([0-9]+)")

TIMEOUT_SESSION = 60 * 5
TIMEOUT_CACHE = 60 * 5 / 2

TZ_EETLIJST = pytz.timezone("Europe/Amsterdam")
TZ_UTC = pytz.timezone("UTC")


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Eetlijst Sensor."""

    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)

    try:
        api = EetlijstApi(username, password)

        sensors = []
        # Handle all containers
        for resident in api.residents:
            sensors.append(EetlijstSensor(api, api.accountname, resident))

        add_entities(sensors, True)
    except:  # noqa: E722 pylint: disable=bare-except
        _LOGGER.error("Error setting up Eetlijst sensor")


class EetlijstApi:
    """Class to interface with Synology DSM API."""

    def __init__(self, username, password):
        """Initialize the API wrapper class."""

        self.username = username
        self.password = password

        self.session = None
        self.cache = {}

        # Initialize None
        self.accountname = None
        self.residents = None
        self.statuses = None

        self._get_session()
        self.get_statuses()

    def get_statuses(self, limit=None):
        content = self._main_page()
        soup = self._get_soup(content)

        # Find all names
        self.residents = [x.nobr.b.text for x in soup.find_all(
            ["th", "a"], title=RE_RESIDENTS)]

        # Grap the list name
        self.accountname = soup.find(["head", "title"]).text.replace(
            "Eetlijst.nl - ", "", 1).strip()

        # Find the main table by first navigating to a unique cell.
        start = soup.find(["table", "tbody", "tr", "th"], width="80")
        if not start:
            raise ScrapingError("Cannot parse status table")

        rows = start.parent.parent.find_all("tr")

        # Iterate over each status row
        has_deadline = False
        pattern = None
        results = []
        start = 0

        for row in rows:
            # Check for limit
            if limit and len(results) >= limit:
                break

            # Skip header rows
            if len(row.find_all("th")) > 0:
                continue

            # Check if the list uses deadlines
            if len(results) == 0:
                has_deadline = bool(
                    row.find(["td", "a"], href=RE_JAVASCRIPT_VS_1))

            if has_deadline:
                start = 2
                pattern = RE_JAVASCRIPT_VS_2
            else:
                start = 1
                pattern = RE_JAVASCRIPT_K

            # Match date and deadline
            matches = re.search(pattern, str(row.renderContents()))
            timestamp = datetime.fromtimestamp(
                int(matches.group(1)), tz=TZ_UTC)

            # Parse each cell for diner status
            statuses = []
            for index, cell in enumerate(row.find_all("td")):
                if index < start:
                    continue

                # Count statuses
                images = str(cell.renderContents())
                nop = images.count("nop.gif")
                kook = images.count("kook.gif")
                eet = images.count("eet.gif")
                leeg = images.count("leeg.gif")

                # Match numbers, in case there are more than 4 images
                extra = RE_DIGIT.findall(cell.text)
                extra = int(extra[0]) if extra else 1

                # Set the data
                if nop > 0:
                    value = 0
                elif kook > 0 and eet == 0:
                    value = kook
                elif kook > 0 and eet > 0:
                    value = kook + (eet * extra)
                elif eet > 0:
                    value = -1 * (eet * extra)
                elif leeg > 0:
                    value = None
                else:
                    raise ScrapingError("Cannot parse diner status.")

                # Append to results
                statuses.append(value)

            # Append to results
            results.append(StatusRow(
                timestamp=timestamp,
                deadline=timestamp if has_deadline else None,
                statuses=dict(zip(self.residents, statuses))))

        return results

    def _get_session(self, is_retry=False, renew=True):
        # Start a session
        if self.session is None:
            if not renew:
                return
            self._login()

        # Check if session is still valid
        session, valid_until = self.session

        if valid_until < self._now():
            if not renew:
                return

            if is_retry:
                raise SessionError("Unable to renew session.")
            else:
                self.session = None
                return self._get_session(is_retry=True)

        return session

    def _login(self):
        # Verify username and password
        if self.username is None and self.password is None:
            raise LoginError("Cannot login without username/password.")

        # Create request
        payload = {
            "login": self.username,
            "pass": self.password
        }
        response = requests.get(BASE_URL + "login.php", params=payload)

        # Check for errors
        if response.status_code != 200:
            raise SessionError("Unexpected status code: %d" %
                               response.status_code)

        if "r=failed" in response.url:
            raise LoginError(
                "Unable to login. Username and/or password incorrect.")

        # Get session parameter
        query_string = urllib.parse.urlparse(response.url).query
        query_array = urllib.parse.parse_qs(query_string)

        try:
            self.session = (
                query_array.get("session_id")[0], self._timeout(seconds=TIMEOUT_SESSION))
        except IndexError:
            raise ScrapingError("Unable to strip session id from URL")

        # Login redirects to main page, so cache it
        self.cache["main_page"] = (response.content.decode(
            response.encoding), self._timeout(seconds=TIMEOUT_CACHE))

    def _main_page(self, is_retry=False, data=None):
        if data is None:
            data = {}

        # Check if in cache
        response = self._from_cache("main_page")
        if response is None:  # not in cache, so get it from website
            payload = {
                "session_id": self._get_session()
            }
            payload.update(data)

            response = requests.get(BASE_URL + "main.php", params=payload)
            # Check for errors
            if response.status_code != 200:
                raise SessionError(
                    "Unexpected status code: %d" % response.status_code)

            # Session expired
            if "login.php" in response.url:
                self._clear_cache()

                # Determine to retry or not
                if is_retry:
                    raise SessionError("Unable to retrieve page: main.php")
                else:
                    return self._main_page(is_retry=True, data=data)

            # Convert to string, we don't need the rest anymore
            response = response.content.decode(response.encoding)

        # Update cache and session
        self.session = (self.session[0], self._timeout(
            seconds=TIMEOUT_SESSION))
        self.cache["main_page"] = (
            response, self._timeout(seconds=TIMEOUT_CACHE))

        return response

    def _from_cache(self, key):
        try:
            response, valid_until = self.cache[key]
        except KeyError:
            return None
        return response if self._now() < valid_until else None

    def _clear_cache(self):
        """
        Clear the internal cache and reset session.
        """
        self.session = None
        self.cache = {}

    def _get_soup(self, content):
        return BeautifulSoup(content, "html.parser")

    def _now(self):
        """
        Return current datetime object with UTC timezone.
        """
        return datetime.now(tz=TZ_UTC)

    def _timeout(self, seconds):
        """
        Helper to calculate datetime for now plus some seconds.
        """
        return self._now() + timedelta(seconds=seconds)

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Update function for updating api information."""
        self.statuses = self.get_statuses()


class StatusRow(object):
    """
    Represent one row of the dinner status table. A status row has a timestamp,
    a deadline and a list of statuses (resident -> status).
    """

    def __init__(self, timestamp, deadline, statuses):
        self.timestamp = timestamp
        self.deadline = deadline
        self.statuses = statuses

    def __repr__(self):
        return "StatusRow(timestamp={}, deadline={}, statuses={})".format(self.timestamp, self.deadline, self.statuses)


class EetlijstSensor(Entity):
    """Representation of a Eetlijst Sensor."""

    def __init__(self, api, accountname, resident):
        """Initialize the sensor."""
        self.var_units = None
        self.var_icon = 'mdi:stove'
        self.accountname = accountname
        self.resident = resident
        self._api = api
        self._state = None

    @property
    def name(self):
        """Return the name of the sensor, if any."""
        return "{}_{}".format(self.accountname, self.resident)

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self.var_icon

    @property
    def state(self):
        """Return the state of the sensor."""

        # get status of today
        status = self._api.statuses[0].statuses[self.resident]
        if status is None:
            value = "?"
        elif status == 0:
            value = "No dinner"
        elif status == 1:
            value = "Cook"
        elif status == -1:
            value = "Dinner"
        elif status > 1:
            value = "Cook + %d" % (status - 1)
        elif status < -1:
            value = "Dinner + %d" % (-1 * status - 1)
        return value

    @property
    def unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        return self.var_units

    def update(self):
        """Get the latest data for the states."""
        if self._api is not None:
            self._api.update()

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return {
            ATTR_ATTRIBUTION: CONF_ATTRIBUTION,
        }


class Error(Exception):
    """
    Base Eetlijst error.
    """
    pass


class LoginError(Error):
    """
    Error class for bad logins.
    """
    pass


class SessionError(Error):
    """
    Error class for session and/or other errors.
    """
    pass


class ScrapingError(Error):
    """
    Error class for scraping related errors.
    """
    pass
