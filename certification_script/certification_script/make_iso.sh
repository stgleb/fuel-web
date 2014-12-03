#!/bin/bash
set -x
set -e 
set -o pipefail

ISO_PATH=/media/data/fuel-5.1.1-28-2014-11-20_21-01-00.iso
ISO_MNT_FOLDER=/mnt/iso1
TMP_FOLDER=/media/fuel_remake_iso
SOURCE_ROOT=~/workspace/fsert
CERT_PATH=certification_script/certification_script
TEST_PATH=fuelweb_tests

DOCKER_IMAGE="$ISO_MNT_FOLDER/docker/images/fuel-images.tar.lrz"
NEW_DOCKER_IMAGE="$TMP_FOLDER/fuel-images.tar.lrz"
WHOLE_TAR_FILE="$TMP_FOLDER/fuel-images.tar"
NAILGUIN_TAR_FILE="$TMP_FOLDER/nailgun.tar"
NAILGUN_CONTAINER_TMP_FOLDER="$TMP_FOLDER/nailgun"
NAILGUN_CONTENT_TMP_FOLDER="$TMP_FOLDER/nailgun_fs"
IMAGE_SCRIPT_FOLDER="$NAILGUN_CONTENT_TMP_FOLDER/usr/lib/python2.6/site-packages"
WHOLE_ISO_TMP="$TMP_FOLDER/image"

function repack_containers_archive() {
    pushd $TMP_FOLDER
    rm -f "$WHOLE_TAR_FILE"
    sudo tar -cf "$WHOLE_TAR_FILE" *
    popd

    rm -f "$NEW_DOCKER_IMAGE"
    lrzip "$WHOLE_TAR_FILE" -o "$NEW_DOCKER_IMAGE"    
}

function using_docker_file() {
    DOCKER_IMAGE_TAR=$1
    SCRIPT_FOLDER=$2

    set +e 
    set +o pipefail
    NAILGUN_IMAGE_ID=`docker images | grep nailgun | awk '{print $3}'`
    set -e 
    set -o pipefail

    
    if [ ! -z "$NAILGUN_IMAGE_ID" ] ; then
        docker rmi $NAILGUN_IMAGE_ID
    fi

    docker load -i "$DOCKER_IMAGE_TAR"
    NAILGUN_IMAGE_NAME=`docker images | grep nailgun | awk '{print $1}'`

    echo "FROM $NAILGUN_IMAGE_NAME" > $SOURCE_ROOT/Dockerfile
    echo "COPY $CERT_PATH /usr/lib/python2.6/site-packages" >> $SOURCE_ROOT/Dockerfile
    echo "COPY $TEST_PATH /usr/lib/python2.6/site-packages" >> $SOURCE_ROOT/Dockerfile

    docker build --force-rm=true -t $NAILGUN_IMAGE_NAME $SOURCE_ROOT
    rm $SOURCE_ROOT/Dockerfile
    rm $DOCKER_IMAGE_TAR
    docker save $NAILGUN_IMAGE_NAME > $DOCKER_IMAGE_TAR
}

function using_cp() {
    tar -xf "$NAILGUIN_TAR_FILE" -C "$NAILGUN_CONTAINER_TMP_FOLDER"

    NAILGUN_CONT_TAR=`find "$NAILGUN_CONTAINER_TMP_FOLDER" -size +200M`
    tar -xf "$NAILGUN_CONT_TAR" -C "$NAILGUN_CONTENT_TMP_FOLDER"

    cp -R "$SCRIPT_FOLDER" "$IMAGE_SCRIPT_FOLDER"

    rm -f "$NAILGUN_CONT_TAR"

    pushd $NAILGUN_CONTENT_TMP_FOLDER
    sudo tar -cf "$NAILGUN_CONT_TAR" *

    cd "$NAILGUN_CONTAINER_TMP_FOLDER"
    rm -f "$NAILGUIN_TAR_FILE"
    sudo tar -cf "$NAILGUIN_TAR_FILE" *
    popd
}

function clean() {
    sudo umount "$ISO_MNT_FOLDER"
    rm -rf $TMP_FOLDER/*
}

function prepare_dirs() {
    mkdir -p "$TMP_FOLDER"
    mkdir -p "$NAILGUN_CONTAINER_TMP_FOLDER"
    mkdir -p "$NAILGUN_CONTENT_TMP_FOLDER"
    mkdir -p "$WHOLE_ISO_TMP"
}

function main() {
    # prepare_dirs

    # sudo mount -o loop "$ISO_PATH" "$ISO_MNT_FOLDER"
    
    # lrzuntar -O "$TMP_FOLDER" "$DOCKER_IMAGE" 

    # using_docker_file "$NAILGUIN_TAR_FILE" "$SCRIPT_FOLDER"

    # repack_containers_archive

    # cp -r "$ISO_MNT_FOLDER" "$WHOLE_ISO_TMP"

    SUBFOLDER=`basename $ISO_MNT_FOLDER`
    WHOLE_ISO_TMP="$WHOLE_ISO_TMP/$SUBFOLDER"
    sudo rm -rf "$WHOLE_ISO_TMP/rr_moved"

    LOCAL_IMAGES_ARCHIVE="$WHOLE_ISO_TMP/docker/images/fuel-images.tar.lrz"
    sudo rm -f "$LOCAL_IMAGES_ARCHIVE"
    sudo cp "$NEW_DOCKER_IMAGE" "$LOCAL_IMAGES_ARCHIVE"

    sudo mkisofs -r -V "FUEL_CERT_ISO" -J -T -R -b isolinux/isolinux.bin \
                -no-emul-boot -boot-load-size 4 -boot-info-table \
                -o "$TMP_FOLDER/fuel_cert_iso.iso" "$WHOLE_ISO_TMP"
    echo "Results are stored in $TMP_FOLDER/fuel_cert_iso.iso"
}

main






