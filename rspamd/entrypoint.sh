#!/bin/ash

#
# Copyright (C) 2026 Genius Dynamics
# SPDX-License-Identifier: GPL-3.0-or-later
#

# The rspamd of Postal, built like the mail-rspamd image of ns8-mail:
# rspamd with its Redis backends (persistent and volatile) and a local
# Unbound resolver for the DNS lists.

# shellcheck shell=dash disable=SC3045

set -e

if [ $# -eq 0 ]; then
    : "${RSPAMD_adminpw:?the controller password is required}"

    reload-config

    mkdir -p -m 0755 /run/redis
    chown redis:redis /run/redis
    su -s /bin/ash - redis -c "exec /usr/bin/redis-server /etc/redis-persistent.conf" </dev/null &
    su -s /bin/ash - redis -c "exec /usr/bin/redis-server /etc/redis-volatile.conf" </dev/null &

    # Local Unbound DNS server (UDP port 11336)
    /usr/sbin/unbound-anchor -v || :
    /usr/sbin/unbound -d <&- &

    mkdir -v -m 0750 -p /run/rspamd
    chown -c rspamd:rspamd /run/rspamd
    /usr/bin/rspamd -u rspamd -g rspamd -f <&- &

    wait -n
    exit $?
else
    exec "${@}"
fi
