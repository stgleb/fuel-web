import json

import sys

import sys
sys.path.insert(0, '../lib/requests')
import requests

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
    elif method == 'DELETE':
        response = requests.delete(url)
    elif method == 'PATCH':
        response = requests.patch(url, data_str)
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


class RestObj(object):
    def __str__(self):
        res = ["{}({}):".format(self.__class__.__name__, self.name)]
        for k,v in sorted(self.__dict__.items()):
            if k != 'name':
                res.append("    {}={!r}".format(k, v))
        return "\n".join(res)


class Node(RestObj):
    pass


class Cluster(RestObj):
    pass


def get_all_nodes():
    for node_desc in api_request('/api/nodes', 'GET'):
        n = Node()
        n.__dict__.update(node_desc)
        yield n


def set_node_name(node, name):
    api_request('/api/nodes', 'PUT', [{'id': node.id, 'name': name}])


def get_clusters():
    for cluster_desc in api_request('/api/clusters', 'GET'):
        n = Cluster()
        n.__dict__.update(cluster_desc)
        yield n
