"""Protocol constants for the Skylink Orbit Home cloud.

Recovered from the Orbit Home Android app (``com.mtqqdemo.skylink``, v3.7) and
confirmed against the live service with real hardware (Skylink GDO, firmware
``WF2012021040204``).

Architecture
------------
* **REST** (``skyhm_api_s.jsp``) is only needed for login. Every call is a signed
  ``POST ...?cmd=<cmd>``; the signature is an MD5 over timestamp/cmd/data plus a
  static app secret (see :func:`orbitclient.client.sign`).
* **MQTT over TLS** carries everything else: the device list, live state pushes,
  and door/light commands. Credentials are the account number (``acc_no``,
  returned by login) and the account password.
"""

from __future__ import annotations

from pathlib import Path

# ---- REST -------------------------------------------------------------------

API_URL = "https://iot.skyhm.net:8444/skylinkhub_crm/skyhm_api_s.jsp"
#: Static secret mixed into REQ-SIGNATURE by the official app.
API_SIGN_SECRET = "8uHDSF77ueRmLlKkl67"

CMD_LOGIN = "act_login"

#: ``result`` codes seen from the REST API.
RESULT_OK = 0
RESULT_LOGIN_NAME_NOT_FOUND = 11
RESULT_BAD_SIGNATURE = 25

# ---- MQTT -------------------------------------------------------------------

# The app connects to ssl://34.214.223.70:1899; that IP is iot.skyhm.net and the
# broker's certificate is issued for that name, so we use it and keep full
# hostname verification.
MQTT_HOST = "iot.skyhm.net"
MQTT_PORT = 1899
MQTT_KEEPALIVE = 30

#: The broker serves only its leaf certificate (no intermediate), so standard
#: clients cannot build a chain. This bundle holds the RapidSSL TLS RSA CA G1
#: intermediate and the DigiCert Global Root G2 it chains to.
CA_BUNDLE = Path(__file__).with_name("orbit_ca.pem")

TOPIC_BASE = "skylink/things/client/{acc_no}"
#: Publish "{}" here to request the full device list...
TOPIC_GET = TOPIC_BASE + "/get"
#: ...which arrives here as {"data": [hub, ...]}.
TOPIC_GET_RESULT = TOPIC_BASE + "/get/result"
#: Partial state pushes: {"data": {"hub_id": ..., "reported": {...}}}.
TOPIC_UPDATE_RESULT = TOPIC_BASE + "/update/result"
#: Commands are published here.
TOPIC_DESIRE = TOPIC_BASE + "/desire"

# ---- Commands (desired.mdev.ctrlgdo.cmd) --------------------------------------

#: Momentary "wall button" press. Observed cycle on real hardware:
#: closed -> opening -> (press) stopped -> (press) closing -> closed, i.e. from
#: "stopped" the door reverses its previous direction of travel.
CTRL_PRESS = 0
#: Light on/off - explicit (idempotent) commands, both confirmed on hardware.
#: GDO hubs do not report light state, so it cannot be read back (and the wall
#: console's single light button toggles it without telling the cloud).
CTRL_LIGHT_ON = 3
CTRL_LIGHT_OFF = 4

DEFAULT_TIMEOUT = 15.0
