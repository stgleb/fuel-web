from setuptools import find_packages
from setuptools import setup

setup(
    name='certification_script',
    version='1.0',
    description='Hardware certification script',
    long_description="""Hardware certification script""",
    author='Mirantis Inc.',
    author_email='product@mirantis.com',
    url='http://mirantis.com',
    install_requires=['PyYAML>=3.10', "argparse>=1.2.1","requests>=2.2.1",
                      'netaddr', 'python-keystoneclient'],
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'cert = certification_script.main:main',
        ],
    }
)