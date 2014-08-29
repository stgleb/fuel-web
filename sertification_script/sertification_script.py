import json
import requests
import yaml
import time


FUEL_BASE_URL = "localhost:8000"
CONFIG_PATH = "/etc/sert-script/config.yaml"


def api_request(url, method, data=None):
    url = FUEL_BASE_URL + url

    if data is None:
        data = ''
    data_str = json.dumps(data)

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
    response = api_request('/api/clusters', 'POST')

    return response['id']


def get_unallocated_nodes(num_nodes, timeout):
    nodes_allocated = 0

    while timeout > 0:
        response = api_request('/api/nodes', 'GET')
        timeout -= 1

        nodes_allocated = len([x for x in response if x['cluster'] is None])
        if nodes_allocated >= num_nodes:
            return response
        time.sleep(1)

    raise Exception('Timeout exception')


def add_node_to_cluster(cluster_id, node_id, roles):
    data = {}
    data['pending_roles'] = roles
    data['cluster_id']= cluster_id
    data['id'] = node_id
    data['pending_addition'] = True

    api_request('/api/nodes', 'PUT', data)


def deploy(cluster_id, timeout):
    api_request('/api/cluster/' + str(cluster_id) + '/changes', 'PUT')

    response = api_request('/api/tasks?cluster_id=' + str(cluster_id), 'GET')

    t = timeout
    while t > 0:
        if response['status'] == 'operational':
            break
        time.sleep(1)
        t -= 1
    else:
        raise Exception('Cluster deploy error')

    t = timeout
    response = api_request('/api/tasks?tasks=' + str(cluster_id), 'GET')

    while timeout > 0:
        flag = True

        for task in response:
            if task['status'] != 'ready':
                flag = False

                if task['status'] == 'error':
                    raise Exception('Task execution error')
        if flag:
            break
        time.sleep(1)
        t -= 1
    else:
        raise Exception('Tasks timeout error')


def main():
    config = parse_config()

    cluster_id = create_cluster()

    num_nodes = config.get('NODES_NUMBER')
    timeout = config.get('TIMEOUT')
    nodes = get_unallocated_nodes(num_nodes,timeout)

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