# Postal for NethServer 8

<div align="center">
  <img src="ui/src/assets/module_default_logo.png" alt="Postal Logo" width="120" height="120">
  
  [![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
  [![GitHub Actions](https://github.com/geniusdynamics/ns8-postal/workflows/Test%20module/badge.svg)](https://github.com/geniusdynamics/ns8-postal/actions)
  [![NethServer 8](https://img.shields.io/badge/NethServer-8-orange)](https://github.com/NethServer/ns8-core)
</div>

## 📧 Overview

**Postal** is a complete and fully featured mail server for use by websites & web servers. Think Sendgrid, Mailgun or Postmark but open source and ready for you to run on your own servers.

This module provides seamless integration of Postal with [NethServer 8](https://github.com/NethServer/ns8-core), offering:

- 🚀 **Full-featured mail server** - Send, receive, and manage emails
- 🔒 **Built-in security** - DKIM, SPF, and bounce handling
- 📊 **Comprehensive analytics** - Track deliveries, opens, and clicks
- 🌐 **Web-based interface** - Modern UI for mail management
- 🔧 **API access** - RESTful API for integration
- 📈 **High performance** - Built for scale and reliability

## 🚀 Quick Start

### Installation

Install the Postal module on your NethServer 8 instance:

```bash
add-module ghcr.io/geniusdynamics/postal:latest 1
```

**Example output:**
```json
{
  "module_id": "postal1", 
  "image_name": "postal", 
  "image_url": "ghcr.io/geniusdynamics/postal:latest"
}
```

### Configuration

Configure your Postal instance (assuming instance name is `postal1`):

```bash
api-cli run configure-module --agent module/postal1 --data - <<EOF
{
  "host": "mail.yourdomain.com",
  "http2https": true,
  "lets_encrypt": true
}
EOF
```

#### Configuration Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `host` | string | ✅ | Fully qualified domain name (e.g., `mail.example.com`) |
| `http2https` | boolean | ✅ | Force HTTPS redirection |
| `lets_encrypt` | boolean | ✅ | Enable Let's Encrypt SSL certificate |

### Access Your Mail Server

After configuration, Postal will be available at:
- **Web Interface**: `https://your-configured-host`
- **SMTP**: Port 2525
- **IMAP**: Port 2143

## 🔧 Management Commands

### Get Current Configuration

```bash
api-cli run get-configuration --agent module/postal1
```

### Update Module

```bash
api-cli run update-module --data '{
  "module_url": "ghcr.io/geniusdynamics/postal:latest",
  "instances": ["postal1"],
  "force": true
}'
```

### Uninstall

```bash
remove-module --no-preserve postal1
```

## 🏗️ Architecture

### Services

The module deploys the following containerized services:

- **postal-app**: Main Postal application server
- **postal-smtp-app**: SMTP service for sending emails
- **postal-worker-app**: Background worker for processing tasks
- **mariadb-app**: Database backend
- **caddy-app**: Web server and reverse proxy

### Network Configuration

- **Port 5000**: Internal web interface (proxied through Traefik)
- **Port 2525**: SMTP service
- **Port 2143**: IMAP service

### Data Persistence

Persistent data is stored in:
- Database files and configurations
- Mail queues and logs
- SSL certificates (if Let's Encrypt is enabled)

## 🔍 Advanced Configuration

### Smarthost Integration

Postal automatically integrates with NethServer 8's [smarthost configuration](https://nethserver.github.io/ns8-core/core/smarthost/):

- Configuration is discovered from Redis keys
- The `bin/discover-smarthost` script refreshes settings on startup
- Changes are automatically applied via event handlers

### Custom Configuration Files

Key configuration templates:
- `imageroot/templates/postal.yml.j2` - Main Postal configuration
- `imageroot/templates/Caddyfile.j2` - Web server configuration

## 🛠️ Development & Debugging

### Debug Commands

1. **Check environment variables:**
   ```bash
   runagent -m postal1 env
   ```

2. **Enter agent environment:**
   ```bash
   runagent -m postal1
   ```

3. **View running containers:**
   ```bash
   runagent -m postal1
   podman ps
   ```

4. **Inspect container environment:**
   ```bash
   podman exec postal-app env
   ```

5. **Access container shell:**
   ```bash
   podman exec -ti postal-app sh
   ```

### Project Structure

```
ns8-postal/
├── imageroot/                 # Module runtime files
│   ├── actions/              # Module actions (configure, restore, etc.)
│   ├── bin/                  # Utility scripts
│   ├── events/               # Event handlers
│   ├── systemd/              # Systemd service definitions
│   └── templates/            # Configuration templates
├── ui/                       # Web interface
│   ├── src/                  # Vue.js application source
│   └── public/               # Static assets and metadata
├── tests/                    # Automated tests
└── build-images.sh          # Image building script
```

## 🧪 Testing

Run the automated test suite:

```bash
./test-module.sh <NODE_ADDR> ghcr.io/geniusdynamics/postal:latest
```

Tests are implemented using [Robot Framework](https://robotframework.org/) and cover:
- Module installation and configuration
- Service health checks
- Basic functionality validation

### Manual Testing

1. **Verify services are running:**
   ```bash
   runagent -m postal1
   systemctl --user status postal.service
   ```

2. **Check logs:**
   ```bash
   podman logs postal-app
   ```

## 🌍 Internationalization

The module supports multiple languages through [Weblate](https://hosted.weblate.org/projects/ns8/).

**Supported Languages:**
- English (en)
- German (de)
- Spanish (es)
- Italian (it)
- Portuguese (pt, pt_BR)
- Basque (eu)

**Contributing Translations:**
1. Join the [NethServer Weblate project](https://hosted.weblate.org/projects/ns8/)
2. Add translations for the `postal` component
3. Submit pull requests for new language files

## 📚 Documentation

- **Postal Documentation**: [docs.postalserver.io](https://docs.postalserver.io/)
- **NethServer 8 Core**: [ns8-core documentation](https://nethserver.github.io/ns8-core/)
- **Module API Reference**: Auto-generated from code comments

## 🤝 Contributing

We welcome contributions! Please see our [contribution guidelines](CONTRIBUTING.md) for details.

### Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/geniusdynamics/ns8-postal.git
   cd ns8-postal
   ```

2. **Build development images:**
   ```bash
   ./build-images.sh
   ```

3. **Run tests:**
   ```bash
   ./test-module.sh localhost:9999 postal:latest
   ```

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/geniusdynamics/dev/issues)
- **Documentation**: [Postal Documentation](https://docs.postalserver.io/)
- **Community**: [NethServer Community](https://community.nethserver.org/)
- **Commercial Support**: [support@genius.ke](mailto:support@genius.ke)

## 📄 License

This project is licensed under the [GNU General Public License v3.0](LICENSE).

```
Copyright (C) 2023 Genius Dynamics

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
```

## 👥 Authors

- **Genius Dynamics** - [support@genius.ke](mailto:support@genius.ke)
- **NethServer Community** - [community.nethserver.org](https://community.nethserver.org/)

---

<div align="center">
  Made with ❤️ by the <a href="https://github.com/geniusdynamics">Genius Dynamics</a> team<br>
  Powered by <a href="https://github.com/NethServer/ns8-core">NethServer 8</a>
</div>
