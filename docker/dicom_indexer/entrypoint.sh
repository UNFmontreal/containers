#!/bin/bash

export CONTAINER_ID=$(basename $(cat /proc/1/cpuset))
GITLAB_TOKEN_SECRET=$(cat /var/run/secrets/dicom_bot_gitlab_token 2>/dev/null)
export GITLAB_TOKEN=${GITLAB_TOKEN_SECRET:=$GITLAB_TOKEN}
S3_ID=$(cat /var/run/secrets/s3_id 2>/dev/null)
S3_SECRET=$(cat /var/run/secrets/s3_secret 2>/dev/null)
export AWS_ACCESS_KEY_ID=${S3_ID:=$AWS_ACCESS_KEY_ID} AWS_SECRET_ACCESS_KEY=${S3_SECRET:=$AWS_SECRET_ACCESS_KEY}
export GITLAB_API_URL=https://${CI_SERVER_HOST}/api/v4
export GIT_SSH_PORT=${GIT_SSH_PORT:=222}

mkdir -p ~/.ssh
# only export keys when deploying as a service on swarm
# TODO: should try using gitlab runner mechanism if not
if [ -n "${GITLAB_TOKEN}" ] ; then
	# generate container specific ssh-key
	ssh-keygen -f  /root/.ssh/id_rsa -N ''
	# register it for dicom_bot user
	echo 'registering the ssh key'
	export ssh_key_json=$(curl -X POST -F "private_token=${GITLAB_TOKEN}" \
	  -F "title="${HOSTNAME} -F "key=$(cat ~/.ssh/id_rsa.pub)" \
	  "${GITLAB_API_URL}/user/keys")
	export ssh_key_id=$(jq .id <<< "$ssh_key_json")
fi

git config --global init.defaultBranch main
ssh-keyscan -p ${GIT_SSH_PORT} -H ${CI_SERVER_HOST} | install -m 600 /dev/stdin $HOME/.ssh/known_hosts

# run whatever command was passed (storescp or python index_dicoms directly)
$@

if [ -n "${GITLAB_TOKEN}" ] ; then
	# unregister the temporary ssh key
	curl -X DELETE -F "private_token=${GITLAB_TOKEN}" "${GITLAB_API_URL}/user/keys/${ssh_key_id}"
fi
