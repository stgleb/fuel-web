import json

import sys

import sys
import time

sys.path.insert(0, '../lib/requests')
import requests

FUEL_BASE_URL = ''

logger = None


def set_logger(log):
    global logger
    logger = log


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
        for k, v in sorted(self.__dict__.items()):
            if k != 'name':
                res.append("    {}={!r}".format(k, v))
        return "\n".join(res)


class Node(RestObj):

    def set_node_name(self, name):
        api_request('/api/nodes', 'PUT', [{'id': self.id, 'name': name}])



class Cluster(RestObj):

    def add_node(self, node_id, roles):
        data = {}
        data['pending_roles'] = self.roles
        data['cluster_id'] = self.id
        data['id'] = node_id
        data['pending_addition'] = True
        logger.debug("Adding node %s to cluster..." % node_id)

        api_request('/api/nodes', 'PUT', [data])

    def deploy(self, timeout):
        logger.debug("Starting deploy...")
        api_request('/api/clusters/' + str(self.id) + '/changes',
                    'PUT')

        for _ in range(timeout):
            cluster = api_request('/api/clusters/' + str(self.id))
            if cluster['status'] == 'operational':
                break
            time.sleep(1)
        else:
            raise Exception('Cluster deploy timeout error')

        for _ in range(timeout):
            response = api_request('/api/tasks?tasks=' + str(cluster_id), 'GET')

            for task in response:
                if task['status'] == 'error':
                    raise Exception('Task execution error')
            else:
                break
            time.sleep(1)
        else:
            raise Exception('Tasks timeout error')

    def delete_cluster(self):
        api_request('/api/clusters/' + str(self.id), 'DELETE')


def get_all_nodes():
    for node_desc in api_request('/api/nodes', 'GET'):
        n = Node()
        n.__dict__.update(node_desc)
        yield n


def get_clusters():
    for cluster_desc in api_request('/api/clusters', 'GET'):
        n = Cluster()
        n.__dict__.update(cluster_desc)
        yield n


def create_empty_cluster(cluster_desc):
    print "Creating new cluster %s" % cluster_desc['name']
    data = {}
    data['nodes'] = []
    data['tasks'] = []
    data['name'] = cluster_desc['name']
    data['release'] = cluster_desc['release']
    data['mode'] = cluster_desc['deployment_mode']
    data['net_provider'] = cluster_desc['settings']['net_provider']
    cluster_response = api_request('/api/clusters', 'POST', data)

    cluster = Cluster()
    cluster.__dict__.update(cluster_response)

    return cluster