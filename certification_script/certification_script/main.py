import sys
import os.path
import logging.config
from optparse import OptionParser

import yaml

import fuel_rest_api
import cert_script as cs

sys.path.insert(0, '../lib/requests')


DEFAULT_CONFIG_PATH = 'config.yaml'


def parse_config(cfg_path):
    with open(cfg_path) as f:
        return yaml.load(f.read())


def parse_command_line():
    parser = OptionParser("usage: %prog [options] arg1")

    parser.add_option('-p', '--password',
                      help='password for email', default=None)

    parser.add_option('-c', '--config',
                      help='config file path', default=DEFAULT_CONFIG_PATH)

    parser.add_option('-u', '--fuelurl',
                      help='fuel rest url', default="http://172.18.201.16:8000/")

    options, _ = parser.parse_args()

    result = {}
    result['password'] = options.password
    result['config'] = options.config
    result['fuelurl'] = options.fuelurl

    return result


def merge_config(config, command_line):
    if command_line.get('password') is not None:
        config['report']['mail']['password'] = command_line.get('password')
    config['fuelurl'] = command_line['fuelurl']


def setup_logger(config):
    with open(config['log_settings']) as f:
        cfg = yaml.load(f)

    logging.config.dictConfig(cfg)

    cs.set_logger(logging.getLogger('clogger'))
    fuel_rest_api.set_logger(logging.getLogger('clogger'))


def main():

    # prepare and config
    args = parse_command_line()
    config = parse_config(args['config'])
    merge_config(config, args)
    setup_logger(config)
    logger = logging.getLogger('clogger')
    conn = fuel_rest_api.Urllib2HTTP(config['fuelurl'], echo=True)

    test_run_timeout = config.get('testrun_timeout', 3600)

    path = os.path.join(os.path.dirname(DEFAULT_CONFIG_PATH),
                        config['tests']['clusters_directory'])

    clusters = cs.load_all_clusters(path)

    tests_cfg = config['tests']['tests']
    for _, test_cfg in tests_cfg.iteritems():
        cluster = clusters[test_cfg['cluster']]

        tests_to_run = test_cfg['suits']

        cluster_id = 7
        #with cs.make_cluster(conn, cluster, auto_delete=True) as cluster_id:
        if 7 == 7:
            results = cs.run_all_tests(conn,
                                       cluster_id,
                                       test_run_timeout,
                                       tests_to_run)

            tests = []
            for testset in results:
                tests.extend(testset['tests'])

            failed_tests = [test for test in tests
                            if test['status'] == 'failure']

            for test in failed_tests:
                logger.debug(test['name'])
                logger.debug(" "*10 + 'Failure message: ' + test['message'])

            cs.send_results(config['report']['mail'], tests)

    return 0


if __name__ == "__main__":
    exit(main())
