# Custom components for Home Assistant

[![maintainer](https://img.shields.io/badge/maintainer-Sander%20Huisman%20-blue.svg?style=for-the-badge)](https://github.com/Sanderhuisman)

## Components

* [Docker Monitor](#docker_monitor)
* [Eetlijst sensor](#eetlijst)
* [Luftdaten](#luftdaten)

### Docker Monitor <a name="docker_monitor"></a>

The Docker monitor allows to monitor statistics and turn on/off containers. The monitor can connected to a Deamon through the url parameter. When home assistant is used within a Docker container, the Deamon can be mounted as followows `-v /var/run/docker.sock:/var/run/docker.sock`.

#### Configuration

To use the `docker_monitor` in your installation, add the following to your `configuration.yaml` file:

```yaml
# Example configuration.yaml entry
docker_monitor:
  containers:
    - homeassistant_home-assistant_1
    - homeassistant_mariadb_1
    - homeassistant_mosquitto_1
  monitored_conditions:
    - utilization_version
    - container_status
    - container_memory_usage
    - container_memory_percentage_usage
    - container_cpu_percentage_usage
```

##### Configuration variables

| Parameter            | Type                     | Description                                                           |
| -------------------- | ------------------------ | --------------------------------------------------------------------- |
| url                  | string       (Optional)  | Host URL of Docker daemon. Defaults to `unix://var/run/docker.sock`.  |
| scan_interval        | time_period  (Optional)  | Update interval. Defaults to 10 seconds.                              |
| containers           | list         (Optional)  | Array of containers to monitor. Defaults to all containers.           |
| monitored_conditions | list         (Optional)  | Array of conditions to be monitored. Defaults to all conditions       |

| Condition                         | Description               | Unit  |
| --------------------------------- | ------------------------- | ----- |
| utilization_version               | Docker version            | -     |
| container_status                  | Container status          | -     |
| container_image                   | Container image           | -     |
| container_cpu_percentage_usage    | CPU usage                 | %     |
| container_memory_usage            | Memory usage              | MB    |
| container_memory_percentage_usage | Memory usage              | %     |
| container_network_up              | Network total upstream    | MB    |
| container_network_down            | Network total downstream  | MB    |

### Eetlijst Sensor <a name="eetlijst"></a>

An Eetlijst sensor to monitor the eat/cook status of your student home.

#### Configuration

To use `eetlijst` in your installation, add the following to your `configuration.yaml` file:

```yaml
# Example configuration.yaml entry
sensor:
  - platform: eetlijst
    username: !secret eetlijst_username
    password: !secret eetlijst_password
```

##### Configuration variables

| Parameter             | Type                    | Description   |
| --------------------- | ----------------------- | ------------- |
| username              | string       (Required) | Username      |
| password              | string       (Required) | Password      |

### Lufdaten Sensor <a name="luftdaten"></a>

A custom Luftdaten sensor to monitor polution of a station.

#### Configuration

To use `luftdaten_cu` in your installation, add the following to your `configuration.yaml` file:

```yaml
# Example configuration.yaml entry
sensor:
  - platform: luftdaten_cu
    sensorid: 15307
    monitored_conditions:
      - P1
      - P2
```

##### Configuration variables

| Parameter             | Type                    | Description                                                     |
| --------------------- | ----------------------- | --------------------------------------------------------------- |
| sensorid              | int          (Required) | Sensor id of the lufdaten sensor to be monitored.               |
| monitored_conditions  | list         (Optional) | Array of conditions to be monitored. Defaults to all conditions |

| Condition                         | Description           | Unit  |
| --------------------------------- | --------------------- | ----- |
| temperature                       | Temperature           | °C    |
| humidity                          | Container status      | %     |
| pressure                          | Air pressure          | Pa    |
| P1                                | PM10                  | µg/m3 |
| P2                                | PM2.5                 | µg/m3 |

## About

## Contributing
