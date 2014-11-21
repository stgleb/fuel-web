#!/bin/sh

DEST=/tmp/certification_script
CONT_PATH=/opt/certification_script

function copy_code_from_local() {
    ssh root@172.18.201.16 "rm -rf $DEST"
    scp -r . root@72.18.201.16:$DEST
}

function copy_code_from_container() {
    ssh root@172.18.201.16 "docker cp fuel-core-5.0.1-nailgun:$CONT_PATH $DEST"
    scp -r . root@72.18.201.16:$DEST
}

function dump_cluster() {
    ssh root@172.18.201.16 "cd $DEST/certification_script/certification_script && python main.py -s AUTO"
}

function run_tests() {
    ssh root@172.18.201.16 "cd $DEST/certification_script/certification_script && python main.py -r"
}
