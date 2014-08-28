import json
import requests
import yaml

FUEL_BASE_URL = "localhost:8000"
CONFIG_PATH = "/etc/sert-script/config.yaml"


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


def parse_config():
    with open(CONFIG_PATH) as f:
        config_data = f.read()
    return yaml.load(config_data)


def create_cluster():
    pass


def get_unallocated_nodes():
    pass


def add_node_to_cluster():
    pass


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