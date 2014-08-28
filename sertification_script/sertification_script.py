import requests
import json
import requests
import yaml
import time


FUEL_BASE_URL = "localhost:8000"
CONFIG_PATH = "/etc/sert-script/config.yaml"


def load_config(config_file_name):
    stream = open(config_file_name, 'r')
    config = yaml.load(stream)

config = load_config(config_file_name)

def api_request(url, method, data=None):
    url = FUEL_BASE_URL + url
    data_str = json.dumps(data)
    response = {}

    if method == 'GET':
        response = requests.get(url)
    elif method == 'POST':
        response = requests.post(url, data_str)
    elif method == 'PUT':
        response = requests.put(url, data_str)
    else:
        raise Exception("Unknown method: %s" % method)

    return json.load(response)

def parse_config():
    with open(CONFIG_PATH) as f:
        config_data = f.read()
    return yaml.load(config_data)


def create_cluster():
    pass
def create_cluster(config):

    data = {}
    # read config info from config to data
    response = api_request(FUEL_BASE_URL + '/clusters','POST',data)

    return response['id']

def get_unallocated_nodes(num_nodes):
    nodes_allocated = 0
    timeout = 10

    while nodes_allocated < num_nodes and timeout > 0:
        response = api_request(FUEL_BASE_URL + '/nodes','GET')
        timeout += 1

        nodes_allocated = len([x for x in response if x['cluster'] is None])
        time.sleep(1)

    return response




[{"id":2,"cluster_id":6,"pending_roles":["controller"],"pending_addition":true}]
def add_node_to_cluster(cluster_id, node_id, roles):
    data = {}
    data['pending_roles'] = roles
    api_request(FUEL_BASE_URL + '/api/nodes','PUT',data)


def deploy():
    pass


def main():
    config = parse_config()

    cluster_id = create_cluster()

    num_nodes = config.get('NODES_NUMBER')
    nodes = get_unallocated_nodes(num_nodes)

    num_controllers = config.get('NUM_CONTROLLERS')
    num_storages = config.get('NUM_STORAGES')
    num_computes = config.get('NUM_COMPUTES')

    nodes_roles_mapping = []
    nodes_roles_mapping.extend(
        [(nodes.pop()['id'], 'controller') for _ in range(num_controllers)])
    nodes_roles_mapping.extend(
        [(nodes.pop()['id'], 'storage') for _ in range(num_storages)])
    nodes_roles_mapping.extend(
        [(nodes.pop()['id'], 'compute') for _ in range(num_computes)])

    for node_id, role in nodes_roles_mapping:
        add_node_to_cluster(cluster_id, node_id, roles=[role])

    deploy(cluster_id)

    # TODO: Wait until deploy finished;

    # TODO: run tests

    # TODO: get test results

if __name__ == "__main__":
    main()