#!/bin/bash

CONTAINER_ID=$(basename $(cat /proc/1/cpuset))
GITLAB_TOKEN_SECRET=/var/run/secrets/dicom_bot_gitlab_token

# only export keys when deploying as a service on swarm
# TODO: should try using gitlab runner mechanism if not
if [ -e $GITLAB_TOKEN_SECRET ] ; then
	# generate container specific ssh-key
	ssh-keygen -f  /root/.ssh/id_rsa -N ''
	# register it for dicom_bot user
	curl -X POST -F "private_token=$(cat $GITLAB_TOKEN_SECRET)" \
	  -F "title="$(cat /etc/hostname)${CONTAINER_ID:0:12} -F "key=$(cat ~/.ssh/id_rsa.pub)" \
	  "${GITLAB_API_URL}/user/keys"
	fi

git config --global init.defaultBranch main


# example
# /usr/bin/storescp \
#  -aet DICOM_SERVER_SEQUOIA\
#  -pm\
#  -od $DICOM_TMP_DIR -su ''\
#  --eostudy-timeout ${STORESCP_STUDY_TIMEOUT:=60} \
#  --exec-on-eostudy "python3 $DICOM_ROOT/exec_on_study_received.py #p " 2100 >> $DICOM_DATA_ROOT/storescp.log

# run whatever command was passed (storescp or python index_dicoms directly)
echo $@
bash -c "$@"

if [ -e $GITLAB_TOKEN_SECRET ] ; then
	# unregister the temporary ssh key
	curl -X DELETE -F "private_token=$(cat $GITLAB_TOKEN_SECRET)" \
	  -F "title="$(cat /etc/hostname)${CONTAINER_ID:0:12}
	  "${GITLAB_API_URL}/user/keys"
fi
