from __future__ import annotations

import requests
import urllib3
from requests.adapters import HTTPAdapter, Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def session_with_retry() -> requests.Session:
    session = requests.Session()
    session.verify = False
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session
