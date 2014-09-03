import time
import glob
import os.path
import smtplib
import logging

from logging import config
from optparse import OptionParser
from email.mime.text import MIMEText

import yaml
from fuel_rest_api import api_request, set_fuel_base_url


FUEL_BASE_URL = "http://localhost:8000"
# CONFIG_PATH = "/etc/sert-script/config.yaml"
CONFIG_PATH = 'config.yaml'

with open('logging.yaml', 'rt') as f:
    cfg = yaml.load(f)

config.dictConfig(cfg)
logger = logging.getLogger('clogger')

def parse_config():
    with open(CONFIG_PATH) as f:
        config_data = f.read()
    return yaml.load(config_data)


def parse_command_line():
    parser = OptionParser("usage: %prog [options] arg1")
    d = {}
    parser.add_option('-p', '--password', dest='password', help='password for email')
    (options, args) = parser.parse_args()
    d['password'] = options.password

    return d


def merge_config(config, command_line):
    if config['report']['mail'].get('password') is None:
        config['report']['mail']['password'] = command_line.get('password')


def get_unallocated_nodes(num_nodes, timeout):
    logger.debug("Waiting for %s nodes to be discovered..." % num_nodes)
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
    logger.debug("Adding node %s to cluster..." % node_id)

    api_request('/api/nodes', 'PUT', [data])


def deploy(cluster_id, timeout):
    logger.debug("Starting deploy...")
    api_request('/api/clusters/' + str(cluster_id) + '/changes',
                'PUT')

    for _ in range(timeout):
        cluster = api_request('/api/clusters/' + str(cluster_id))
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


def run_all_tests(cluster_id, timeout):
    # Get all available tests
    logger.debug("Running tests...")
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


def send_results(mail_config, tests):
    server = smtplib.SMTP(mail_config['smtp_server'], 587)
    server.starttls()
    server.login(mail_config['login'], mail_config['password'])

    # Form message body
    failed_tests = [test for test in tests if test['status'] == 'failure']
    msg = '\n'.join([test['name'] + '\n        ' + test['message']
                     for test in failed_tests])

    msg = MIMEText(msg)
    msg['Subject'] = 'Test Results'
    msg['To'] = mail_config['mail_to']
    msg['From'] = mail_config['mail_from']

    logger.debug("Sending results by email...")
    server.sendmail(mail_config['mail_from'],
                    [mail_config['mail_to']],
                    msg.as_string())
    server.quit()


def load_all_clusters(path):
    res = {}
    for fname in glob.glob(os.path.join(path, "*.yaml")):
        try:
            cluster = yaml.load(open(fname).read())
            res[cluster['name']] = cluster
        except Exception as exc:
            msg = "Failed to load cluster from file {}: {}".format(
                fname, exc)
            logger.error(msg)
    return res


def create_empty_cluster(name, cluster):
    print "Creating new cluster %s" % name
    data = {}
    data['nodes'] = []
    data['tasks'] = []
    data['name'] = name
    data['release'] = cluster['release']
    data['mode'] = cluster['deployment_mode']
    data['net_provider'] = cluster['net_provider']
    response = api_request('/api/clusters', 'POST', data)
    return response['id']


def delete_cluster(cluster_id):
    api_request('/api/clusters/' + str(cluster_id), 'DELETE')


def deploy_cluster(name, cluster):
    cluster_id = create_empty_cluster(name, cluster)

    num_controllers = cluster['num_controllers']
    num_computes = cluster['num_computes']
    num_storages = cluster['num_storage']

    num_nodes = num_controllers + num_computes + num_storages
    logger.debug("Waiting for %d nodes to be discovered..." % num_nodes)
    nodes_discover_timeout = cluster.get('nodes_discovery_timeout', 3600)
    deploy_timeout = cluster.get('DEPLOY_TIMEOUT', 3600)

    nodes = get_unallocated_nodes(num_nodes, nodes_discover_timeout)

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
    return cluster_id


def main():
    config = parse_config()
    command_line = parse_command_line()
    merge_config(config, command_line)

    set_fuel_base_url(config['fuel_api'].get('url'))
    test_run_timeout = config.get('testrun_timeout', 3600)
    config['clusters'] = load_all_clusters('clusters/')

    for cluster in config['clusters'].values():
        cluster_id = deploy_cluster(config['name'], cluster)
        results = run_all_tests(cluster_id, test_run_timeout)

        tests = []
        for testset in results:
            tests.extend(testset['tests'])

        failed_tests = [test for test in tests if test['status'] == 'failure']
        for test in failed_tests:
            logger.debug(test['name'])
            logger.debug(" "*10 + 'Failure message: ' + test['message'])

        send_results(config['report']['mail'], tests)

        delete_cluster(cluster_id)

if __name__ == "__main__":
    parse_command_line()
    exit(main())
