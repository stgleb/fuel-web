import json
import requests
import sys
import time
import yaml


FUEL_BASE_URL = "http://localhost:8000"
CONFIG_PATH = "/etc/sert-script/config.yaml"


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


def parse_config():
    with open(CONFIG_PATH) as f:
        config_data = f.read()
    return yaml.load(config_data)


def create_cluster(config):
    cluster_name = config.get('NAME')
    print "Creating new cluster %s" % cluster_name
    data = {}
    data['nodes'] = []
    data['tasks'] = []
    data['name'] = cluster_name
    data['release'] = config.get('RELEASE')
    data['mode'] = config.get('DEPLOYMENT_MODE')
    data['net_provider'] = config.get('NET_PROVIDER')
    response = api_request('/api/clusters', 'POST', data)

    return response['id']


def get_unallocated_nodes(num_nodes, timeout):
    print "Waiting for %s nodes to be discovered..." % num_nodes
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
    data['cluster_id'] = cluster_id
    data['id'] = node_id
    data['pending_addition'] = True
    print "Adding node %s to cluster..." % node_id

    api_request('/api/nodes', 'PUT', [data])


def deploy(cluster_id, timeout):
    print "Starting deploy..."
    api_request('/api/clusters/' + str(cluster_id) + '/changes',
                'PUT')
    t = timeout

    while t > 0:
        cluster = api_request('/api/clusters/' + str(cluster_id))
        if cluster['status'] == 'operational':
            break
        time.sleep(1)
        t -= 1
    else:
        raise Exception('Cluster deploy timeout error')

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


def run_all_tests(cluster_id, timeout):
    # Get all available tests
    print "Running tests..."
    testsets = api_request('/ostf/testsets/%s' % str(cluster_id))
    test_data = []
    for testset in testsets:
        test_data.append(
            {'testset': testset['id'],
             'tests': [],
             'metadata': {'cluster_id': cluster_id}})
        # Run all available tests

    headers = {'Content-type': 'application/json'}
    testruns = api_request('/ostf/testruns', 'POST', data=test_data,
                           headers=headers)
    started_at = time.time()
    finished_testruns = []
    while testruns:
        if time.time() - started_at < timeout:
            for testrun in testruns:
                testrun_resp = api_request('/ostf/testruns/%s' % testrun['id'])
                if testrun_resp['status'] != 'finished':
                    time.sleep(5)
                    continue
                else:
                    finished_testruns.append(testrun_resp)
                    testruns.remove(testrun)
        else:
            raise Exception('Timeout error')
    return finished_testruns


def main():
    config = parse_config()

    cluster_id = create_cluster(config)

    num_nodes = config.get('NODES_NUMBER')
    nodes_discover_timeout = config.get('NODES_DISCOVERY_TIMEOUT')
    deploy_timeout = config.get('DEPLOY_TIMEOUT')
    test_run_timeout = config.get('TESTRUN_TIMEOUT')

    nodes = get_unallocated_nodes(num_nodes, nodes_discover_timeout)

    num_controllers = config.get('NUM_CONTROLLERS')
    num_storages = config.get('NUM_STORAGES')
    num_computes = config.get('NUM_COMPUTES')

    nodes_roles_mapping = []
    nodes_roles_mapping.extend(
        [(nodes.pop()['id'], 'controller') for _ in range(num_controllers)])
    nodes_roles_mapping.extend(
        [(nodes.pop()['id'], 'cinder') for _ in range(num_storages)])
    nodes_roles_mapping.extend(
        [(nodes.pop()['id'], 'compute') for _ in range(num_computes)])

    for node_id, role in nodes_roles_mapping:
        add_node_to_cluster(cluster_id, node_id, roles=[role])

    deploy(cluster_id, deploy_timeout)
    results = run_all_tests(cluster_id, test_run_timeout)

    tests = []
    for testset in results:
        tests.extend(testset['tests'])

    failed_tests = [test for test in tests if test['status'] == 'failure']
    for test in failed_tests:
        print test['name']
        print " "*10 + 'Failure message: ' + test['message']

    # TODO: remove deletion

if __name__ == "__main__":
    try:
        main()
        sys.exit(0)
    except Exception as e:
        print "Script failed"
        import traceback
        traceback.print_exc()
        sys.exit(1)
