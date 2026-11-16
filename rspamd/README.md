# postal-rspamd

rspamd for the Postal module, built like the `mail-rspamd` image of
[ns8-mail](https://github.com/NethServer/ns8-mail): Alpine with rspamd,
two Redis backends (persistent: Bayes and history; volatile: the rest) on
unix sockets and a local Unbound resolver (UDP 11336) for the DNS lists.

It runs in the postal pod, so it never conflicts with the rspamd of
ns8-mail, which uses the network of the node (ports 11332-11336).

## TCP ports (pod network)

- 11333 normal worker: Postal scans the messages here
- 11334 controller: web interface and API, published on
  `127.0.0.1:<second TCP port of the module>` for Traefik and the host-network
  worker of Postal

## Environment variables

- `RSPAMD_adminpw` controller password (`state/rspamd.env`, 0600)

## Volumes

- `/etc/rspamd/override.d` custom configuration (`rspamd-override`)
- `/var/lib/rspamd` rspamd data (`rspamd-data`)
- `/var/lib/redis` Redis data (`rspamd-redis`)

## Commands

- `reload-config` render the templates and send a HUP signal to rspamd
