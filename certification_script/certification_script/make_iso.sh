#!/bin/bash
set -x
set -e 
set -o pipefail

ISO_PATH=/media/data/fuel-5.1.1-28-2014-11-20_21-01-00.iso
ISO_MNT_FOLDER=/mnt/iso1
TMP_FOLDER=/media/fuel_remake_iso
CERT_PATH=~/workspace/fsert/certification_script/certification_script
TEST_PATH=~/workspace/fsert/fuelweb_tests

DOCKER_IMAGES_FOLDER="$TMP_FOLDER/container_images"
DOCKER_IMAGE="$ISO_MNT_FOLDER/docker/images/fuel-images.tar.lrz"
NEW_DOCKER_IMAGE="$DOCKER_IMAGES_FOLDER/fuel-images.tar.lrz"
WHOLE_TAR_FILE="$DOCKER_IMAGES_FOLDER/fuel-images.tar"
NAILGUIN_TAR_FILE="$DOCKER_IMAGES_FOLDER/nailgun.tar"
NAILGUN_CONTAINER_TMP_FOLDER="$DOCKER_IMAGES_FOLDER/nailgun"
NAILGUN_CONTENT_TMP_FOLDER="$DOCKER_IMAGES_FOLDER/nailgun_fs"
IMAGE_SCRIPT_FOLDER="$NAILGUN_CONTENT_TMP_FOLDER/usr/lib/python2.6/site-packages"
WHOLE_ISO_TMP="$TMP_FOLDER/image"
SCRIPTS_TMP_FOLDER_FOR_DOCKER="$TMP_FOLDER/files"

function repack_containers_archive() {
    pushd $TMP_FOLDER
    rm -f "$WHOLE_TAR_FILE"
    sudo tar -cf "$WHOLE_TAR_FILE" *
    popd

    rm -f "$NEW_DOCKER_IMAGE"
    lrzip "$WHOLE_TAR_FILE" -o "$NEW_DOCKER_IMAGE"    
}

function using_docker_file() {
    set +e 
    set +o pipefail
    NAILGUN_IMAGE_ID=`docker images | grep nailgun | awk '{print $3}'`
    set -e 
    set -o pipefail

    
    if [ ! -z "$NAILGUN_IMAGE_ID" ] ; then
        docker rmi $NAILGUN_IMAGE_ID
    fi

    docker load -i "$NAILGUIN_TAR_FILE"
    NAILGUN_IMAGE_NAME=`docker images | grep nailgun | awk '{print $1}'`

    CERT_PATH_DIR_NAME=`basename $CERT_PATH`
    TEST_PATH_DIR_NAME=`basename $TEST_PATH`

    cp -r "$CERT_PATH" "$SCRIPTS_TMP_FOLDER_FOR_DOCKER"
    cp -r "$TEST_PATH" "$SCRIPTS_TMP_FOLDER_FOR_DOCKER"

    DOCKERFILE=$SCRIPTS_TMP_FOLDER_FOR_DOCKER/Dockerfile
    echo "FROM $NAILGUN_IMAGE_NAME" > $DOCKERFILE
    echo "COPY $CERT_PATH_DIR_NAME /usr/lib/python2.6/site-packages" >> $DOCKERFILE
    echo "COPY $TEST_PATH_DIR_NAME /usr/lib/python2.6/site-packages" >> $DOCKERFILE

    docker build --force-rm=true -t $NAILGUN_IMAGE_NAME $SCRIPTS_TMP_FOLDER_FOR_DOCKER
    docker save $NAILGUN_IMAGE_NAME > $NAILGUIN_TAR_FILE
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
    mkdir -p "$SCRIPTS_TMP_FOLDER_FOR_DOCKER"
    mkdir -p "$DOCKER_IMAGES_FOLDER"
}

function remake_iso() {
    cp -r "$ISO_MNT_FOLDER/." "$WHOLE_ISO_TMP"

    sudo rm -rf "$WHOLE_ISO_TMP/rr_moved"

    LOCAL_IMAGES_ARCHIVE="$WHOLE_ISO_TMP/docker/images/fuel-images.tar.lrz"
    sudo rm -f "$LOCAL_IMAGES_ARCHIVE"
    sudo cp "$NEW_DOCKER_IMAGE" "$LOCAL_IMAGES_ARCHIVE"

    sudo mkisofs -r -V "FUEL_CERT_ISO" -J -T -R -b isolinux/isolinux.bin \
                -no-emul-boot -boot-load-size 4 -boot-info-table \
                -o "$TMP_FOLDER/fuel_cert_iso.iso" "$WHOLE_ISO_TMP"
}

function main() {
    prepare_dirs

    # mount iso image
    sudo mount -o loop "$ISO_PATH" "$ISO_MNT_FOLDER"

    # extract_containers_images
    lrzuntar -O "$DOCKER_IMAGES_FOLDER" "$DOCKER_IMAGE" 

    using_docker_file
    repack_containers_archive
    remake_iso

    echo "Results are stored in $TMP_FOLDER/fuel_cert_iso.iso"
}

main







