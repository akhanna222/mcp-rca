# MCP-RCA Quick Start Guide

## One-Command Setup on AWS EC2

```bash
# Clone and setup (10 minutes)
git clone https://github.com/akhanna222/mcp-rca.git
cd mcp-rca
sudo bash scripts/setup_ec2.sh
```

The script will interactively ask for:
- ✓ Anthropic API Key (required)
- ✓ GCP credentials (optional)
- ✓ AWS credentials (optional)
- ✓ Azure credentials (optional)

**That's it!** Service will be running at `http://YOUR-EC2-IP:8000`

---

## Essential Commands

### Service Management
```bash
# Check status
sudo systemctl status mcp-rca.service

# View live logs
sudo journalctl -u mcp-rca.service -f

# Restart service
sudo systemctl restart mcp-rca.service

# Stop service
sudo systemctl stop mcp-rca.service
```

### Health Check
```bash
# Check if service is healthy
curl http://localhost:8000/health

# Test webhook
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"incident":{"incident_id":"test","summary":"Test"}}'
```

### Troubleshooting
```bash
# Port stuck? Clean up and restart
sudo bash scripts/cleanup_ports.sh
sudo systemctl start mcp-rca.service

# View recent errors
sudo journalctl -u mcp-rca.service -n 50 --no-pager

# Check configuration
cd /opt/mcp-rca
source venv/bin/activate
python src/cli.py validate --config config/platform.yaml
```

---

## Get Your API Keys

### Anthropic (Required)
1. Go to: https://console.anthropic.com/settings/keys
2. Click "Create Key"
3. Copy key starting with `sk-ant-...`

### GCP (Optional)
1. Go to: https://console.cloud.google.com/iam-admin/serviceaccounts
2. Create service account with roles:
   - Monitoring Viewer
   - Logging Viewer
3. Create JSON key

### AWS (Optional - Use IAM Role)
1. Go to: https://console.aws.amazon.com/iam/
2. Create role with policies:
   - CloudWatchReadOnlyAccess
   - CloudWatchLogsReadOnlyAccess
3. Attach to EC2 instance

### Azure (Optional)
```bash
az ad sp create-for-rbac \
  --name mcp-rca \
  --role "Monitoring Reader" \
  --scopes /subscriptions/YOUR_SUBSCRIPTION_ID
```

---

## Configure Alert Webhooks

### GCP Cloud Monitoring
```bash
# Webhook URL
http://YOUR-EC2-IP:8000/webhook

# In GCP Console:
# 1. Monitoring → Alerting → Edit Notification Channels
# 2. Add Webhook
# 3. Enter webhook URL
# 4. Use in alert policies
```

### AWS CloudWatch + SNS
```bash
# 1. Create SNS Topic
# 2. Add HTTPS subscription: http://YOUR-EC2-IP:8000/webhook
# 3. Use SNS topic in CloudWatch alarms
```

### Azure Monitor
```bash
# 1. Monitor → Alerts → Action groups
# 2. Add Webhook action
# 3. Webhook URL: http://YOUR-EC2-IP:8000/webhook
# 4. Use in alert rules
```

---

## Project Structure

```
/opt/mcp-rca/              # Application directory
├── config/
│   └── platform.yaml      # Main configuration
├── .env                   # Credentials (SECRET!)
├── venv/                  # Python virtual environment
└── src/                   # Source code

/var/log/mcp-rca/          # Logs directory
├── mcp-rca.log           # Application logs
└── mcp-rca-error.log     # Error logs
```

---

## Common Tasks

### Update Configuration
```bash
# Edit config
sudo nano /opt/mcp-rca/config/platform.yaml

# Validate
cd /opt/mcp-rca && source venv/bin/activate
python src/cli.py validate --config config/platform.yaml

# Restart
sudo systemctl restart mcp-rca.service
```

### Update Credentials
```bash
# Edit credentials
sudo nano /opt/mcp-rca/.env

# Restart
sudo systemctl restart mcp-rca.service
```

### View Logs
```bash
# Live application logs
sudo tail -f /var/log/mcp-rca/mcp-rca.log

# Live error logs
sudo tail -f /var/log/mcp-rca/mcp-rca-error.log

# Last 100 lines
sudo journalctl -u mcp-rca.service -n 100
```

### Clean Restart
```bash
# Stop everything and clean up
sudo bash scripts/cleanup_ports.sh

# Restart service
sudo systemctl start mcp-rca.service

# Or re-run full setup
sudo bash scripts/setup_ec2.sh
```

---

## Security Checklist

- [ ] **HTTPS**: Set up Nginx reverse proxy with Let's Encrypt
- [ ] **Firewall**: Restrict port 8000 to monitoring IPs only
- [ ] **Credentials**: Store `.env` securely (chmod 600)
- [ ] **Updates**: Keep system packages updated
- [ ] **Monitoring**: Monitor the platform itself with CloudWatch

---

## Testing the Platform

### 1. Generate Test Alert from Demo App

```bash
# Run demo microservice (generates errors)
cd /opt/mcp-rca
source venv/bin/activate
python demo/microservice_api.py

# In another terminal, generate traffic
for i in {1..100}; do
  curl -X POST http://localhost:8080/api/documents \
    -H "Content-Type: application/json" \
    -d '{"title":"Test","content":"Data"}'
done
```

### 2. Send Manual Test Alert

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "incident": {
      "incident_id": "test-'$(date +%s)'",
      "summary": "High error rate in API service",
      "state": "open",
      "severity": "CRITICAL",
      "started_at": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
    },
    "project": "my-project"
  }'
```

### 3. Check RCA Results

```bash
# Watch logs for analysis
sudo journalctl -u mcp-rca.service -f | grep -E "(Root cause|RECOMMENDATION)"

# Or view full log
sudo tail -f /var/log/mcp-rca/mcp-rca.log
```

---

## Performance Tuning

```yaml
# Edit config/platform.yaml

alerts:
  max_concurrent_alerts: 20    # Increase for high-volume
  timeout_seconds: 300         # Increase for complex analysis

anthropic:
  max_tokens: 16000           # Decrease to reduce latency
  temperature: 0.0            # Keep at 0 for deterministic results
```

---

## Uninstall

```bash
# Stop and remove everything
sudo systemctl stop mcp-rca.service
sudo systemctl disable mcp-rca.service
sudo rm /etc/systemd/system/mcp-rca.service
sudo rm -rf /opt/mcp-rca
sudo rm -rf /var/log/mcp-rca
sudo userdel -r mcp-rca
sudo systemctl daemon-reload
```

---

## Need Help?

- 📖 **Full Documentation**: `docs/DEPLOYMENT.md`
- 🏗️ **Architecture**: `docs/ARCHITECTURE.md`
- 💼 **Business Case**: `docs/BUSINESS_CASE.md`
- 🚀 **Scripts Guide**: `scripts/README.md`
- 🐛 **Issues**: https://github.com/akhanna222/mcp-rca/issues

---

## What Happens During RCA?

```
1. Alert received → Webhook triggered
2. MCP-RCA analyzes:
   ✓ Metrics (CPU, memory, latency, errors)
   ✓ Logs (error messages, stack traces)
   ✓ Recent changes (deployments, config)
   ✓ Historical patterns
3. Claude AI identifies root cause
4. Generates remediation steps
5. Results logged and returned

Average time: 15-60 seconds
```

---

## Success Metrics

Track these after deployment:

- **MTTR**: Mean Time To Resolution (expect 70-80% reduction)
- **Alert Response Time**: Time from alert to investigation start
- **RCA Accuracy**: % of correct root cause identifications
- **Engineering Hours Saved**: Hours per week saved on incident response
- **On-call Escalations**: Reduction in after-hours pages

---

**Quick Start Version**: 1.0.0
**Last Updated**: 2026-01-09
**Platform Version**: 1.0.0
