import json
import requests
import smtplib
import sys
import time
import yaml
import logging

from optparse import OptionParser
from email.mime.text import MIMEText


# FUEL_BASE_URL = "http://localhost:8000"
CONFIG_PATH = "/etc/sert-script/config.yaml"
# SMTP_SERVER = 'smtp.gmail.com'
# MAIL_TO = "email@gmail.com"
# MAIL_FROM = "email@gmail.com"
# LOGIN = "Example"
# PASS = "Pass"

logger = logging.getLogger('sertification script logger')
logger.setLevel(10)


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


def parse_command_line():
    parser = OptionParser("usage: %prog [options] arg1")
    d = {}
    parser.add_option('-p', '--password', dest='password', default='1234', help='password for email')
    (options, args) = parser.parse_args()
    d['password'] = options.password

    return d


def merge_config(config,command_line):
    pass


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
    logger.log("Waiting for %s nodes to be discovered..." % num_nodes)
    for _ in range(timeout):
        response = api_request('/api/nodes', 'GET')

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
    logger.log("Adding node %s to cluster..." % node_id)

    api_request('/api/nodes', 'PUT', [data])


def deploy(cluster_id, timeout):
    logger.log("Starting deploy...")
    api_request('/api/clusters/' + str(cluster_id) + '/changes',
                'PUT')

    for _ in range(timeout):
        cluster = api_request('/api/clusters/' + str(cluster_id))
        if cluster['status'] == 'operational':
            break
        time.sleep(1)
    else:
        raise Exception('Cluster deploy timeout error')

    t = timeout
    response = api_request('/api/tasks?tasks=' + str(cluster_id), 'GET')

    for _ in range(timeout):
        flag = True

        for task in response:
            if task['status'] == 'error':
                raise Exception('Task execution error')
            elif task['status'] == 'ready':
                break
        else:
            break
        time.sleep(1)
    else:
        raise Exception('Tasks timeout error')


def run_all_tests(cluster_id, timeout):
    # Get all available tests
    logger.log("Running tests...")
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


def send_results(tests):
    server = smtplib.SMTP(SMTP_SERVER, 587)
    server.starttls()
    server.login(LOGIN, PASS)

    # Form message body
    failed_tests = [test for test in tests if test['status'] == 'failure']
    msg = '\n'.join([test['name'] + '\n        ' + test['message']
                     for test in failed_tests])

    msg = MIMEText(msg)
    msg['Subject'] = 'Test Results'
    msg['To'] = MAIL_TO
    msg['From'] = MAIL_FROM

    logger.log("Sending results by email...")
    server.sendmail(MAIL_FROM, [MAIL_TO],
                    msg.as_string())
    server.quit()


def main():
    config_file = parse_config()
    command_line_options = parse_command_line()

    merge_config(config_file,command_line_options)

    for config in config_file['CLUSTERS']:
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
            logger.log(test['name'])
            logger.log(" "*10 + 'Failure message: ' + test['message'])

        send_results(tests)

        # TODO: remove deletion

if __name__ == "__main__":
    parse_command_line()
    exit(main())
