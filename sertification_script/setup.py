from setuptools import find_packages
from setuptools import setup

setup(
    name='sertification_script',
    version='1.0',
    description='Hardware sertification script',
    long_description="""Hardware sertification script""",
    author='Mirantis Inc.',
    author_email='product@mirantis.com',
    url='http://mirantis.com',
    install_requires=['PyYAML==3.10', "argparse==1.2.1","requests==2.2.1"],
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'sert = sertification_script.main:main',
        ],
    }
)