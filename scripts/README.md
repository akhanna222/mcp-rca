# MCP-RCA Setup Scripts

This directory contains automation scripts for deploying and managing the MCP-RCA platform on AWS EC2.

## Scripts Overview

### 1. `setup_ec2.sh` - Complete Automated Setup

**Purpose**: One-command setup of the entire MCP-RCA platform on a fresh EC2 instance.

**What it does**:
1. ✓ Stops all existing services and frees ports
2. ✓ Installs system dependencies (Python 3.10+, git, etc.)
3. ✓ Creates application user and directories
4. ✓ Collects credentials interactively (GCP, AWS, Azure, Anthropic)
5. ✓ Sets up Python virtual environment
6. ✓ Creates configuration files
7. ✓ Validates configuration
8. ✓ Creates systemd service
9. ✓ Configures firewall
10. ✓ Starts the service
11. ✓ Performs health check
12. ✓ Prints setup summary

**Usage**:
```bash
# Run with sudo
sudo bash scripts/setup_ec2.sh

# The script will interactively prompt for:
# - Anthropic API Key (required)
# - GCP credentials (optional)
# - AWS credentials (optional)
# - Azure credentials (optional)
# - Project name and configuration
```

**Requirements**:
- Ubuntu 20.04+ or Amazon Linux 2
- Root/sudo access
- Internet connectivity

**Duration**: ~10-15 minutes

**Output**:
- Service installed at: `/opt/mcp-rca`
- Logs at: `/var/log/mcp-rca/`
- Configuration: `/opt/mcp-rca/config/platform.yaml`
- Systemd service: `mcp-rca.service`

---

### 2. `cleanup_ports.sh` - Port and Service Cleanup

**Purpose**: Stop all MCP-RCA services and free ports before fresh setup or troubleshooting.

**What it does**:
- Stops systemd service
- Stops supervisor processes
- Kills processes on specified port (default: 8000)
- Terminates all MCP-RCA related processes
- Verifies cleanup completion

**Usage**:
```bash
# Clean up default port (8000)
sudo bash scripts/cleanup_ports.sh

# Clean up specific port
sudo bash scripts/cleanup_ports.sh 9000
```

**When to use**:
- Before running `setup_ec2.sh` on a server with existing installation
- When service is stuck or not responding
- When you see "port already in use" errors
- Before manual reinstallation

**Duration**: ~10 seconds

---

## Quick Start Guide

### Fresh EC2 Instance Setup

```bash
# 1. SSH into your EC2 instance
ssh -i your-key.pem ubuntu@your-ec2-ip

# 2. Clone the repository
git clone https://github.com/akhanna222/mcp-rca.git
cd mcp-rca

# 3. Run the setup script
sudo bash scripts/setup_ec2.sh

# 4. Follow the interactive prompts to configure:
#    - Anthropic API Key
#    - Cloud provider credentials (GCP/AWS/Azure)
#    - Project details

# 5. Done! Service is running at http://YOUR-IP:8000
```

### Existing Installation - Clean Restart

```bash
# 1. Stop and clean up
sudo bash scripts/cleanup_ports.sh

# 2. Restart service
sudo systemctl start mcp-rca.service

# Or re-run full setup
sudo bash scripts/setup_ec2.sh
```

---

## Credentials Required

### Anthropic API (Required)

```bash
# Get from: https://console.anthropic.com/settings/keys
ANTHROPIC_API_KEY=sk-ant-...
```

### Google Cloud Platform (Optional)

```bash
# 1. Create service account: https://console.cloud.google.com/iam-admin/serviceaccounts
# 2. Grant roles: Monitoring Viewer, Logging Viewer
# 3. Create JSON key
# 4. Provide during setup:
GCP_PROJECT_ID=your-project-id
GCP_KEY_PATH=/path/to/service-account-key.json
```

### AWS (Optional)

**Option 1: IAM Role (Recommended)**
- Attach IAM role to EC2 instance with policies:
  - `CloudWatchReadOnlyAccess`
  - `CloudWatchLogsReadOnlyAccess`

**Option 2: Access Keys**
```bash
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
```

### Azure (Optional)

```bash
# Create service principal:
# az ad sp create-for-rbac --name mcp-rca --role "Monitoring Reader"

AZURE_SUBSCRIPTION_ID=...
AZURE_TENANT_ID=...
AZURE_CLIENT_ID=...
AZURE_CLIENT_SECRET=...
```

---

## Post-Installation

### Service Management

```bash
# Check status
sudo systemctl status mcp-rca.service

# View logs (live)
sudo journalctl -u mcp-rca.service -f

# View logs (last 100 lines)
sudo journalctl -u mcp-rca.service -n 100

# Restart service
sudo systemctl restart mcp-rca.service

# Stop service
sudo systemctl stop mcp-rca.service

# Start service
sudo systemctl start mcp-rca.service
```

### Health Check

```bash
# Check service health
curl http://localhost:8000/health

# Test webhook endpoint
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "incident": {
      "incident_id": "test-123",
      "summary": "Test alert",
      "state": "open"
    }
  }'
```

### Configuration

```bash
# Edit configuration
sudo nano /opt/mcp-rca/config/platform.yaml

# Validate configuration
cd /opt/mcp-rca
source venv/bin/activate
python src/cli.py validate --config config/platform.yaml

# Restart after changes
sudo systemctl restart mcp-rca.service
```

### Logs

```bash
# Application logs
sudo tail -f /var/log/mcp-rca/mcp-rca.log

# Error logs
sudo tail -f /var/log/mcp-rca/mcp-rca-error.log

# Setup log
sudo cat /var/log/mcp-rca-setup.log
```

---

## Troubleshooting

### Service won't start

```bash
# Check systemd status
sudo systemctl status mcp-rca.service

# Check logs
sudo journalctl -u mcp-rca.service -n 50 --no-pager

# Common issues:
# 1. Port already in use → Run cleanup_ports.sh
# 2. Invalid credentials → Check /opt/mcp-rca/.env
# 3. Config errors → Validate with: python src/cli.py validate
```

### Port already in use

```bash
# Clean up and retry
sudo bash scripts/cleanup_ports.sh
sudo systemctl start mcp-rca.service
```

### Permission issues

```bash
# Fix ownership
sudo chown -R mcp-rca:mcp-rca /opt/mcp-rca
sudo chown -R mcp-rca:mcp-rca /var/log/mcp-rca
```

### API key errors

```bash
# Check environment file
sudo cat /opt/mcp-rca/.env

# Update API key
sudo nano /opt/mcp-rca/.env
sudo systemctl restart mcp-rca.service
```

---

## Security Best Practices

### 1. HTTPS Setup

```bash
# Install Nginx and Certbot
sudo apt-get install nginx certbot python3-certbot-nginx

# Configure reverse proxy
sudo nano /etc/nginx/sites-available/mcp-rca

# Get SSL certificate
sudo certbot --nginx -d your-domain.com
```

### 2. Firewall Configuration

```bash
# Allow only specific IPs (replace with your monitoring IPs)
sudo ufw allow from YOUR_MONITORING_IP to any port 8000

# Or use Nginx reverse proxy and only allow local
sudo ufw deny 8000
sudo ufw allow 80
sudo ufw allow 443
```

### 3. Credential Rotation

```bash
# Update credentials
sudo nano /opt/mcp-rca/.env

# Restart service
sudo systemctl restart mcp-rca.service
```

---

## Uninstall

```bash
# Stop and disable service
sudo systemctl stop mcp-rca.service
sudo systemctl disable mcp-rca.service

# Remove service file
sudo rm /etc/systemd/system/mcp-rca.service
sudo systemctl daemon-reload

# Remove application
sudo rm -rf /opt/mcp-rca
sudo rm -rf /var/log/mcp-rca

# Remove user
sudo userdel -r mcp-rca

# Remove firewall rules
sudo ufw delete allow 8000/tcp
```

---

## Support

- **Documentation**: See `docs/` directory
- **Issues**: https://github.com/akhanna222/mcp-rca/issues
- **Deployment Guide**: `docs/DEPLOYMENT.md`
- **Architecture**: `docs/ARCHITECTURE.md`

---

**Last Updated**: 2026-01-09
