import json

import sys

FUEL_BASE_URL = ''


def api_request(url, method='GET', data=None, headers=None):
    url = FUEL_BASE_URL + url
    if data is None:
        data = ''
    data_str = json.dumps(data)

    if method == 'GET':
        response = requests.get(url)
    elif method == 'POST':
        response = requests.post(url, data_str, headers=headers)
    elif method == 'PUT':
        response = requests.put(url, data_str, headers=headers)
    else:
        raise Exception("Unknown method: %s" % method)

    if response.status_code in range(200, 400):
            return json.loads(response.text)
    else:
        raise Exception(str(response.status_code) +
                        ' error has occured' + response.text)


def set_fuel_base_url(base_url):
    global FUEL_BASE_URL
    FUEL_BASE_URL = base_url