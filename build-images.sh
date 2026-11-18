#!/bin/bash

#
# Copyright (C) 2023 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-3.0-or-later
#

# Terminate on error
set -e

# Prepare variables for later use
images=()
# The image will be pushed to GitHub container registry
repobase="${REPOBASE:-ghcr.io/geniusdynamics}"
# Configure the image name
reponame="postal"
# Node.js 25+ no longer ships Corepack, install it from npm
# renovate: datasource=npm packageName=corepack
corepack_version=0.36.0
# Base of the postal-rspamd image
# renovate: datasource=docker packageName=docker.io/library/alpine
alpine_version=3.24.4

# Create a new empty container image
container=$(buildah from scratch)

# Reuse existing nodebuilder-postal container, to speed up builds
if ! buildah containers --format "{{.ContainerName}}" | grep -q nodebuilder-postal; then
	echo "Pulling NodeJS runtime..."
	buildah from --name nodebuilder-postal -v "${PWD}:/usr/src:Z" docker.io/library/node:26.13.0-slim
	buildah run nodebuilder-postal sh -c "npm install -g corepack@${corepack_version} && corepack enable"
fi

echo "Build static UI files with node..."
buildah run \
	--workingdir=/usr/src/ui \
	--env="NODE_OPTIONS=--openssl-legacy-provider" \
	nodebuilder-postal \
	sh -c "yarn install && yarn build"

# Add imageroot directory to the container image
buildah add "${container}" imageroot /imageroot
buildah add "${container}" ui/dist /ui
# Labels:
# - traefik@node:fulladm: web route, and the certificate of the SMTP host
#   name for STARTTLS (get-certificate, set-certificate)
# - node:fwadm: open the SMTP port of the pod on the node firewall
# - node:portsadm: the two ports of rspamd and ClamAV for installs created
#   with one TCP port
# - three TCP ports, published on 127.0.0.1: the web interface (Traefik),
#   the rspamd controller and clamd of the optional containers
# - images: Postal and MariaDB, the optional ClamAV, pinned versions
#   tracked by Renovate, and the postal-rspamd image built below
buildah config --entrypoint=/ \
	--label="org.nethserver.authorizations=traefik@node:fulladm node:fwadm,portsadm cluster:accountconsumer idp@any:clientadm keycloak@any:clientadm lemonldapng@any:clientadm" \
	--label="org.nethserver.tcp-ports-demand=3" \
	--label="org.nethserver.rootfull=0" \
	--label="org.nethserver.min-core=3.0.0" \
	--label="org.nethserver.images=ghcr.io/postalserver/postal:3.3.7 docker.io/mariadb:13.0.2 docker.io/clamav/clamav:1.5.4 ${repobase}/postal-rspamd:${IMAGETAG:-latest}" \
	"${container}"
# Commit the image
buildah commit "${container}" "${repobase}/${reponame}"

# Append the image URL to the images array
images+=("${repobase}/${reponame}")

#
# rspamd image of the optional rspamd_container setting, built like the
# mail-rspamd image of ns8-mail: rspamd with its Redis backends and a local
# Unbound resolver, on Alpine (see rspamd/README.md)
#
reponame="postal-rspamd"
container=$(buildah from "docker.io/library/alpine:${alpine_version}")
buildah run "${container}" /bin/sh <<'EOF'
set -e
# Software installation order is important to preserve uid and gid allocation:
apk add --no-cache redis
apk add --no-cache rspamd rspamd-controller rspamd-proxy rspamd-fuzzy rspamd-client
apk add --no-cache unbound
# for envsubst
apk add --no-cache gettext
EOF
buildah add "${container}" rspamd/ /
buildah config \
	--volume=/var/lib/redis \
	--volume=/var/lib/rspamd \
	--volume=/etc/rspamd/override.d \
	--entrypoint='["/entrypoint.sh"]' \
	--cmd='' \
	"${container}"
buildah commit "${container}" "${repobase}/${reponame}"
images+=("${repobase}/${reponame}")

#
# Setup CI when pushing to Github.
# Warning! docker::// protocol expects lowercase letters (,,)
if [[ -n "${CI}" ]]; then
	# Set output value for Github Actions
	printf "images=%s\n" "${images[*],,}" >>"${GITHUB_OUTPUT}"
else
	# Just print info for manual push
	printf "Publish the images with:\n\n"
	for image in "${images[@],,}"; do printf "  buildah push %s docker://%s:%s\n" "${image}" "${image}" "${IMAGETAG:-latest}"; done
	printf "\n"
fi
