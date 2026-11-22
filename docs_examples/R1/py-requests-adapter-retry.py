# Documentation example (requests, Advanced Usage > Example: Automatic Retries): a Session with
# HTTPAdapter(max_retries=Retry(total=3, backoff_factor=0.1, status_forcelist=[502, 503, 504], allowed_methods={'POST'})),
# verbatim (the example sets no timeout), placed in the minimal R1 function of the D61 check.
import requests
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


class ProfileError(Exception):
    pass


s = Session()
retries = Retry(
    total=3,
    backoff_factor=0.1,
    status_forcelist=[502, 503, 504],
    allowed_methods={'POST'},
)
s.mount('https://', HTTPAdapter(max_retries=retries))


def get_user_profile(base_url: str, user_id: str) -> dict:
    url = f"{base_url.rstrip('/')}/v1/users/{user_id}"
    try:
        r = s.get(url)
    except requests.RequestException as e:
        raise ProfileError(str(e)) from e
    if r.status_code != 200:
        raise ProfileError(f"status {r.status_code}")
    return r.json()
