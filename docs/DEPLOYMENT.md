# MCP-RCA Deployment Guide: AWS EC2

## Quick Start: Deploy in 30 Minutes

This guide walks you through deploying MCP-RCA on an AWS EC2 instance to monitor GCP, AWS, or Azure infrastructure.

---

## Prerequisites

### What You Need

- **AWS Account** with EC2 access
- **Cloud credentials** for monitoring:
  - GCP: Service account JSON file OR Application Default Credentials
  - AWS: IAM role OR access keys
  - Azure: Service principal credentials
- **Anthropic API Key** ([Get one here](https://console.anthropic.com/))
- **Basic Linux knowledge** (SSH, editing files)

### Estimated Costs

- **EC2 Instance**: ~$50-100/month (t3.large recommended)
- **Anthropic API**: ~$15-30/month (depends on incident volume)
- **Network**: ~$5-10/month
- **Total**: ~$70-140/month

---

## Step 1: Launch EC2 Instance

### 1.1 Create EC2 Instance

```bash
# Via AWS Console:
# 1. Go to EC2 Dashboard
# 2. Click "Launch Instance"
# 3. Use these settings:

Name: mcp-rca-platform
AMI: Ubuntu 22.04 LTS (HVM), SSD Volume Type
Instance Type: t3.large (2 vCPU, 8 GB RAM)
Key Pair: Create new or use existing
Network: Default VPC
Security Group: Create new (see below)
Storage: 30 GB gp3
```

### 1.2 Configure Security Group

```yaml
Security Group Rules:

Inbound:
  - Port 22 (SSH): Your IP only (for management)
  - Port 5000 (HTTP): 0.0.0.0/0 (for alert webhooks)
  - Port 9090 (Metrics): Your IP only (for Prometheus)

Outbound:
  - All traffic: 0.0.0.0/0 (for API calls to GCP/AWS/Azure/Anthropic)
```

### 1.3 Launch and Connect

```bash
# Wait for instance to start, then connect:
ssh -i your-key.pem ubuntu@<EC2_PUBLIC_IP>
```

---

## Step 2: Install Dependencies

### 2.1 Update System

```bash
sudo apt update && sudo apt upgrade -y
```

### 2.2 Install Python 3.11+

```bash
sudo apt install -y python3.11 python3.11-venv python3-pip git
```

### 2.3 Install System Dependencies

```bash
# For GCP monitoring
sudo apt install -y curl wget gnupg

# For process management
sudo apt install -y supervisor
```

---

## Step 3: Clone and Setup Repository

### 3.1 Clone Repository

```bash
cd /opt
sudo git clone https://github.com/yourusername/mcp-rca.git
sudo chown -R ubuntu:ubuntu mcp-rca
cd mcp-rca
```

### 3.2 Create Virtual Environment

```bash
python3.11 -m venv venv
source venv/bin/activate
```

### 3.3 Install Python Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Step 4: Configure Cloud Credentials

Choose the cloud provider(s) you want to monitor:

### Option A: Monitor Google Cloud Platform (GCP)

#### 4.1 Create GCP Service Account

```bash
# In GCP Console:
# 1. Go to IAM & Admin > Service Accounts
# 2. Create Service Account: "mcp-rca-monitor"
# 3. Grant roles:
#    - Monitoring Viewer
#    - Logging Viewer
#    - Service Usage Consumer
# 4. Create and download JSON key
```

#### 4.2 Upload Service Account to EC2

```bash
# From your local machine:
scp -i your-key.pem service-account.json ubuntu@<EC2_IP>:/opt/mcp-rca/config/

# Or use the GCP metadata server (if EC2 is in GCP):
# No credentials needed if using Application Default Credentials
```

#### 4.3 Set Permissions

```bash
cd /opt/mcp-rca
chmod 600 config/service-account.json
```

---

### Option B: Monitor Amazon Web Services (AWS)

#### 4.1 Create IAM Role (Recommended)

```bash
# In AWS Console:
# 1. Go to IAM > Roles > Create Role
# 2. Select: AWS service > EC2
# 3. Attach policies:
#    - CloudWatchReadOnlyAccess
#    - CloudWatchLogsReadOnlyAccess
# 4. Name: "mcp-rca-monitor-role"
# 5. Attach role to your EC2 instance
```

#### 4.2 Alternative: Use Access Keys (Less Secure)

```bash
# Create IAM user with same permissions
# Download access keys
# Configure on EC2:

aws configure
# Enter: Access Key ID
# Enter: Secret Access Key
# Enter: Default region (e.g., us-east-1)
# Enter: Default output format (json)
```

---

### Option C: Monitor Microsoft Azure

#### 4.1 Create Service Principal

```bash
# In Azure Cloud Shell:
az ad sp create-for-rbac \
  --name "mcp-rca-monitor" \
  --role "Reader" \
  --scopes /subscriptions/<SUBSCRIPTION_ID>

# Note the output:
# {
#   "appId": "...",          # Client ID
#   "password": "...",       # Client Secret
#   "tenant": "..."          # Tenant ID
# }
```

#### 4.2 Create Credentials File

```bash
cat > /opt/mcp-rca/config/azure-credentials.json <<EOF
{
  "subscription_id": "YOUR_SUBSCRIPTION_ID",
  "tenant_id": "YOUR_TENANT_ID",
  "client_id": "YOUR_CLIENT_ID",
  "client_secret": "YOUR_CLIENT_SECRET"
}
EOF

chmod 600 /opt/mcp-rca/config/azure-credentials.json
```

---

## Step 5: Configure Anthropic API Key

### 5.1 Create Environment File

```bash
cat > /opt/mcp-rca/.env <<EOF
# Anthropic API Key (REQUIRED)
ANTHROPIC_API_KEY=sk-ant-your-api-key-here

# Optional: Configuration path
RCA_CONFIG_PATH=/opt/mcp-rca/config/platform.yaml

# Optional: Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
EOF

chmod 600 /opt/mcp-rca/.env
```

---

## Step 6: Create Platform Configuration

### 6.1 Choose Configuration Template

```bash
# For single GCP project:
cp examples/config_single_project_gcp.yaml config/platform.yaml

# For multiple projects:
cp examples/config_multi_project.yaml config/platform.yaml
```

### 6.2 Edit Configuration

```bash
nano config/platform.yaml
```

### 6.3 Example: Single GCP Project Configuration

```yaml
version: "1.0.0"

# Anthropic configuration
anthropic:
  model: "claude-3-7-sonnet-20250219"
  max_tokens: 8192
  timeout_seconds: 300.0
  max_retries: 3

# Alert webhook configuration
alerts:
  enabled: true
  host: "0.0.0.0"
  port: 5000
  path: "/alert"
  max_concurrent_alerts: 10

# Platform observability
observability:
  enabled: true
  metrics_port: 9090
  log_level: "INFO"
  log_format: "json"
  structured_logging: true

# Projects to monitor
projects:
  - name: "production"
    display_name: "Production Environment"
    description: "Main production infrastructure"
    provider: "gcp"
    enabled: true

    gcp:
      project_id: "your-gcp-project-id"

      auth:
        method: "service_account"
        service_account_path: "/opt/mcp-rca/config/service-account.json"
        quota_project_id: "your-gcp-project-id"

      monitoring:
        enabled: true
        timeout_seconds: 60.0
        queries:
          - name: "CPU Usage"
            query: 'avg(cpu_usage{project="production"})'
            purpose: "Monitor CPU utilization"
            enabled: true

          - name: "Memory Usage"
            query: 'avg(memory_usage{project="production"})'
            purpose: "Monitor memory utilization"
            enabled: true

          - name: "API Error Rate"
            query: 'rate(api_errors_total[5m])'
            purpose: "Track API errors"
            enabled: true

      logging:
        enabled: true
        default_time_range_minutes: 10.0
        max_log_entries: 1000
        filters:
          - name: "Application Errors"
            filter_query: 'severity>=ERROR'
            purpose: "Application error logs"
            enabled: true

          - name: "System Errors"
            filter_query: 'resource.type="gce_instance" AND severity>=ERROR'
            purpose: "System-level errors"
            enabled: true

    labels:
      environment: "production"
      team: "platform"
```

---

## Step 7: Validate Configuration

### 7.1 Test Configuration Loading

```bash
cd /opt/mcp-rca
source venv/bin/activate

# Validate config syntax
python -c "from src.core.config_manager import ConfigManager; ConfigManager('config/platform.yaml')"

# Should print: "Configuration loaded successfully"
```

### 7.2 Run Full Validation

```bash
python src/cli.py validate --config config/platform.yaml --strict
```

### 7.3 Test Cloud Connectivity

```bash
# For GCP:
python src/cli.py health --config config/platform.yaml

# Expected output:
# ✓ Project: production (gcp)
# ✓ Healthy
```

---

## Step 8: Start the Platform

### Option A: Run Manually (Testing)

```bash
cd /opt/mcp-rca
source venv/bin/activate

# Start server
python src/api/server.py --config config/platform.yaml

# You should see:
# Starting RCA platform
# Application created successfully
# * Running on http://0.0.0.0:5000
```

### Option B: Run with Supervisor (Production)

#### 8.1 Create Supervisor Configuration

```bash
sudo nano /etc/supervisor/conf.d/mcp-rca.conf
```

```ini
[program:mcp-rca]
command=/opt/mcp-rca/venv/bin/python src/api/server.py --config config/platform.yaml
directory=/opt/mcp-rca
user=ubuntu
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/mcp-rca/platform.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
environment=ANTHROPIC_API_KEY="sk-ant-your-key-here",HOME="/home/ubuntu"
```

#### 8.2 Create Log Directory

```bash
sudo mkdir -p /var/log/mcp-rca
sudo chown ubuntu:ubuntu /var/log/mcp-rca
```

#### 8.3 Start with Supervisor

```bash
# Reload supervisor config
sudo supervisorctl reread
sudo supervisorctl update

# Start the service
sudo supervisorctl start mcp-rca

# Check status
sudo supervisorctl status mcp-rca
# Should show: RUNNING

# View logs
sudo tail -f /var/log/mcp-rca/platform.log
```

---

## Step 9: Configure Cloud Monitoring Alerts

### For GCP: Create Alert Policy

```bash
# In GCP Console:
# 1. Go to Monitoring > Alerting
# 2. Create Policy
# 3. Add Condition (e.g., "High API Error Rate")
# 4. Configure Notification Channel:

Channel Type: Webhook
Webhook URL: http://<EC2_PUBLIC_IP>:5000/alert
```

### GCP Alert Policy Example (YAML)

```yaml
# alert-policy.yaml
displayName: "API Error Rate High"
conditions:
  - displayName: "Error rate > 5%"
    conditionThreshold:
      filter: 'metric.type="monitoring.googleapis.com/api_errors"'
      comparison: COMPARISON_GT
      thresholdValue: 0.05
      duration: 60s

notificationChannels:
  - projects/YOUR_PROJECT/notificationChannels/WEBHOOK_ID

documentation:
  content: "API error rate exceeded 5% threshold"
```

---

## Step 10: Verify Everything Works

### 10.1 Test Health Endpoint

```bash
curl http://<EC2_PUBLIC_IP>:5000/health

# Expected:
# {
#   "status": "healthy",
#   "version": "1.0.0",
#   "projects": 1,
#   "enabled_projects": 1
# }
```

### 10.2 Test Metrics Endpoint

```bash
curl http://<EC2_PUBLIC_IP>:9090/metrics

# Should show Prometheus metrics
```

### 10.3 Send Test Alert

```bash
curl -X POST http://<EC2_PUBLIC_IP>:5000/alert \
  -H "Content-Type: application/json" \
  -d '{
    "incident": {
      "summary": "Test alert",
      "documentation": {
        "content": "This is a test"
      },
      "metadata": {
        "project": "production"
      }
    }
  }'

# Expected:
# {
#   "status": "accepted",
#   "message": "Alert processing started"
# }
```

### 10.4 Check Logs

```bash
sudo tail -f /var/log/mcp-rca/platform.log

# You should see:
# Alert processed successfully
# Correlation ID: ...
# Tool calls: ...
```

---

## Step 11: Production Hardening

### 11.1 Enable HTTPS (Recommended)

```bash
# Install Nginx
sudo apt install -y nginx certbot python3-certbot-nginx

# Configure Nginx as reverse proxy
sudo nano /etc/nginx/sites-available/mcp-rca
```

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/mcp-rca /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com
```

### 11.2 Configure Firewall

```bash
# Install UFW
sudo apt install -y ufw

# Configure rules
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS

# Enable firewall
sudo ufw enable
sudo ufw status
```

### 11.3 Setup Automatic Backups

```bash
# Create backup script
sudo nano /usr/local/bin/backup-mcp-rca.sh
```

```bash
#!/bin/bash
BACKUP_DIR="/opt/backups/mcp-rca"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup configuration
tar -czf $BACKUP_DIR/config-$DATE.tar.gz /opt/mcp-rca/config/

# Keep only last 7 days
find $BACKUP_DIR -name "config-*.tar.gz" -mtime +7 -delete
```

```bash
# Make executable
sudo chmod +x /usr/local/bin/backup-mcp-rca.sh

# Add to crontab (daily at 2 AM)
sudo crontab -e
# Add: 0 2 * * * /usr/local/bin/backup-mcp-rca.sh
```

### 11.4 Setup Log Rotation

```bash
sudo nano /etc/logrotate.d/mcp-rca
```

```
/var/log/mcp-rca/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    missingok
    create 0644 ubuntu ubuntu
    postrotate
        supervisorctl restart mcp-rca > /dev/null
    endscript
}
```

---

## Step 12: Monitoring the Platform Itself

### 12.1 Setup CloudWatch Monitoring (AWS)

```bash
# Install CloudWatch agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i amazon-cloudwatch-agent.deb

# Configure agent
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-config-wizard
```

### 12.2 Create CloudWatch Dashboard

```bash
# In AWS Console:
# 1. CloudWatch > Dashboards > Create Dashboard
# 2. Add widgets:
#    - EC2 CPU Utilization
#    - EC2 Memory Usage
#    - Application logs
#    - Custom metrics from /metrics endpoint
```

### 12.3 Setup Prometheus (Optional)

```bash
# Install Prometheus
sudo apt install -y prometheus

# Configure to scrape MCP-RCA metrics
sudo nano /etc/prometheus/prometheus.yml
```

```yaml
scrape_configs:
  - job_name: 'mcp-rca'
    static_configs:
      - targets: ['localhost:9090']
```

---

## Troubleshooting

### Common Issues

#### Issue: "Cannot connect to GCP"

```bash
# Check credentials
cat config/service-account.json | jq .

# Test authentication
python -c "
from google.auth import default
creds, project = default()
print(f'Authenticated as project: {project}')
"
```

#### Issue: "Anthropic API errors"

```bash
# Verify API key
echo $ANTHROPIC_API_KEY

# Test API
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-3-7-sonnet-20250219","max_tokens":10,"messages":[{"role":"user","content":"Hi"}]}'
```

#### Issue: "Port 5000 already in use"

```bash
# Find process using port
sudo lsof -i :5000

# Kill if needed
sudo kill -9 <PID>

# Or use different port
python src/api/server.py --config config/platform.yaml --port 5001
```

#### Issue: "Memory exhausted"

```bash
# Check memory usage
free -h

# Upgrade instance type or add swap:
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Viewing Logs

```bash
# Platform logs
sudo tail -f /var/log/mcp-rca/platform.log

# Supervisor logs
sudo tail -f /var/log/supervisor/supervisord.log

# System logs
sudo journalctl -u mcp-rca -f

# Filter errors only
sudo grep ERROR /var/log/mcp-rca/platform.log
```

---

## Maintenance

### Updating the Platform

```bash
cd /opt/mcp-rca

# Stop service
sudo supervisorctl stop mcp-rca

# Backup current version
cp -r /opt/mcp-rca /opt/mcp-rca.backup

# Pull updates
git pull origin main

# Update dependencies
source venv/bin/activate
pip install --upgrade -r requirements.txt

# Restart service
sudo supervisorctl start mcp-rca

# Check status
sudo supervisorctl status mcp-rca
```

### Scaling Up

```bash
# To handle more load:
# 1. Upgrade EC2 instance type (t3.large → t3.xlarge)
# 2. Increase concurrent alert limit in config:

alerts:
  max_concurrent_alerts: 50  # Increase from 10

# 3. Restart service
sudo supervisorctl restart mcp-rca
```

---

## Multi-Cloud Setup (GCP + AWS + Azure)

### Configuration Example

```yaml
projects:
  # GCP Production
  - name: "gcp-production"
    display_name: "GCP Production"
    provider: "gcp"
    enabled: true
    gcp:
      project_id: "gcp-prod-123"
      auth:
        method: "service_account"
        service_account_path: "/opt/mcp-rca/config/gcp-service-account.json"

  # AWS Production
  - name: "aws-production"
    display_name: "AWS Production"
    provider: "aws"
    enabled: true
    aws:
      account_id: "123456789012"
      auth:
        method: "iam_role"
        region: "us-east-1"

  # Azure Production
  - name: "azure-production"
    display_name: "Azure Production"
    provider: "azure"
    enabled: true
    azure:
      subscription_id: "azure-sub-id"
      auth:
        method: "service_principal"
        tenant_id: "tenant-id"
        client_id: "client-id"
        client_secret: "client-secret"
```

---

## Cost Optimization

### Tips to Reduce Costs

1. **Use Reserved Instances**: Save 30-60% on EC2
2. **Use Spot Instances**: Save 70-90% (for non-critical monitoring)
3. **Right-size Instance**: Start with t3.medium, scale up if needed
4. **Limit Log Retention**: Set `max_log_entries: 500` to reduce API costs
5. **Cache Results**: Enable caching to reduce repeated queries
6. **Schedule Off-hours**: Stop during maintenance windows

---

## Quick Reference

### Service Management

```bash
# Start
sudo supervisorctl start mcp-rca

# Stop
sudo supervisorctl stop mcp-rca

# Restart
sudo supervisorctl restart mcp-rca

# Status
sudo supervisorctl status mcp-rca

# Logs
sudo tail -f /var/log/mcp-rca/platform.log
```

### CLI Commands

```bash
# Validate config
python src/cli.py validate --config config/platform.yaml

# Check health
python src/cli.py health --config config/platform.yaml

# List projects
python src/cli.py projects --config config/platform.yaml

# Test MCP connection
python src/cli.py test-mcp --config config/platform.yaml --project production

# Generate new config
python src/cli.py generate-config --output config/new.yaml --template single-gcp
```

---

## Next Steps

1. ✅ **Monitor**: Watch first few alerts come through
2. ✅ **Tune**: Adjust queries and filters based on results
3. ✅ **Scale**: Add more projects as needed
4. ✅ **Optimize**: Fine-tune prompt templates for your use cases
5. ✅ **Integrate**: Connect with Slack, PagerDuty, etc.

---

## Support

- 📖 [Full Documentation](../README.md)
- 🏗️ [Architecture Guide](ARCHITECTURE.md)
- 💼 [Business Case](BUSINESS_CASE.md)
- 🔍 [RCA Problem Explained](THE_RCA_PROBLEM.md)

---

**Deployment Time**: 30 minutes
**Difficulty**: Intermediate
**Cost**: ~$70-140/month
**Value**: $5.7M annual savings (for 100 incidents/month)
