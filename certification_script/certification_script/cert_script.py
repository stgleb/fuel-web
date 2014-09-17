import time
import glob
import os.path
import pkgutil
import smtplib
import inspect
import functools
import contextlib
from email.mime.text import MIMEText

import yaml

import fuel_rest_api
from tests import base

logger = None

GB = 1024 * 1024 * 1024


def set_logger(log):
    global logger
    logger = log


def find_node_by_requirements(nodes, requirements):
    min_cpu = requirements.get('cpu_count_min') or 0
    max_cpu = requirements.get('cpu_count_max') or 1000
    min_hd = requirements.get('hd_size_min') or 0
    max_hd = requirements.get('hd_size_max') or 10000

    def hd_valid(hd):
        return max_hd >= hd >= min_hd

    def cpu_valid(cpu):
        return max_cpu >= cpu >= min_cpu

    for node in nodes:
        cpu = node.meta['cpu']['total']
        hd = sum(disk['size'] for disk in node.meta['disks']) / GB

        if cpu_valid(cpu) and hd_valid(hd):
            return node
    return None


def match_nodes(conn, nodes_descriptions, timeout):
    required_nodes_count = len(nodes_descriptions)
    logger.debug("Waiting for nodes {} to be discovered...".format(required_nodes_count))
    result = []

    for _ in range(timeout):
        free_nodes = [node for node in fuel_rest_api.get_all_nodes(conn)
                      if node.cluster is None]

        if len(free_nodes) < required_nodes_count:
            time.sleep(1)
        else:
            node_mac_mapping = dict([(node.mac.upper(), node) for
                                     node in free_nodes])
            for node_description in nodes_descriptions.values():
                found_node = None
                node_mac = node_description.get('mac')
                if node_mac is not None:
                    node_mac = node_mac.upper()
                    if node_mac in node_mac_mapping:
                        found_node = node_mac_mapping[node_mac]
                elif 'requirements' in node_description:
                    found_node = find_node_by_requirements(free_nodes, \
                                    node_description['requirements'])
                else:
                    found_node = free_nodes[0]

                if found_node is None:
                    print "Can't found node for requirements", node_mac, node_description.get('requirements')
                    break

                free_nodes.remove(found_node)
                result.append((node_description, found_node))
            else:
                return result

    raise Exception('Timeout exception')


def find_test_classes():
    test_classes = []
    for loader, name, _ in pkgutil.iter_modules(['tests']):
        module = loader.find_module(name).load_module(name)
        test_classes.extend([member for name, member in
                             inspect.getmembers(module)
                             if inspect.isclass(member) and
                                issubclass(member, base.BaseTests)])
    return test_classes


def run_all_tests(cluster_id, timeout, tests_to_run, fuel_url):
    test_classes = find_test_classes()
    results = []
    for test_class in test_classes:
        test_class_inst = test_class(fuel_url, cluster_id, timeout)
        available_tests = test_class_inst.get_available_tests()
        results.extend(test_class_inst.run_tests(
            set(available_tests) & set(tests_to_run)))
    return results


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


def deploy_cluster(conn, cluster_desc):
    cluster = fuel_rest_api.create_empty_cluster(conn, cluster_desc)
    nodes_discover_timeout = cluster_desc.get('nodes_discovery_timeout', 3600)
    deploy_timeout = cluster_desc.get('DEPLOY_TIMEOUT', 3600)
    nodes_info = cluster_desc['nodes']

    for node_desc, node in match_nodes(conn, nodes_info, nodes_discover_timeout):
        cluster.add_node(node, node_desc['roles'])

    cluster.deploy(deploy_timeout)
    return cluster


@contextlib.contextmanager
def make_cluster(conn, cluster, auto_delete=False):
    if auto_delete:
        for cluster_obj in fuel_rest_api.get_all_clusters(conn):
            if cluster_obj.name == cluster['name']:
                cluster_obj.delete()
                wd = fuel_rest_api.with_timeout("Wait cluster deleted", 60)
                wd(lambda co: not co.check_exists())(cluster_obj)

    c = deploy_cluster(conn, cluster)
    try:
        yield c
    finally:
        c.delete()


def with_cluster(conn, config_path):
    cluster_desc = yaml.load(open(config_path).read())

    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            with make_cluster(conn, cluster_desc) as cluster:
                arg_spec = inspect.getargspec(f)
                if 'cluster_id' in arg_spec.args[len(arg_spec.defaults) - 1:]:
                    kwargs['cluster_id'] = cluster.id
                return f(*args, **kwargs)
        return wrapper
    return decorator


