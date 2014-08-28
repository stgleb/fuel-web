import requests
import json


FUEL_BASE_URL = "localhost:8000"


def api_request(url, method, data=None):
    url = FUEL_BASE_URL + url
    data_str = json.dumps(data)
    if method == 'GET':
        requests.get(url)
    elif method == 'POST':
        requests.post(url, data_str)
    elif method == 'PUT':
        requests.put(url, data_str)
    else:
        raise Exception("Unknown method: %s" % method)


def create_cluster():
    pass


def get_unallocated_nodes():
    pass


def add_node_to_cluster():
    pass


def deploy():
    pass
