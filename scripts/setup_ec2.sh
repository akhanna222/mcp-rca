#!/bin/bash
################################################################################
# MCP-RCA Platform - EC2 Automated Setup Script
#
# This script automates the complete setup of the MCP-RCA platform on AWS EC2.
# It will:
#   1. Stop all existing services and free ports
#   2. Collect all required credentials interactively
#   3. Install dependencies
#   4. Configure the platform
#   5. Set up systemd service
#   6. Start the platform
#
# Usage:
#   sudo bash scripts/setup_ec2.sh
#
# Requirements:
#   - Ubuntu 20.04+ or Amazon Linux 2
#   - Root or sudo access
#   - Internet connectivity
################################################################################

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_DIR="/opt/mcp-rca"
APP_USER="mcp-rca"
CONFIG_FILE="${APP_DIR}/config/platform.yaml"
ENV_FILE="${APP_DIR}/.env"
LOG_DIR="/var/log/mcp-rca"
PORT=8000

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo -e "${BLUE}=================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}=================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

prompt_input() {
    local prompt="$1"
    local var_name="$2"
    local default="$3"
    local is_secret="${4:-false}"

    if [ -n "$default" ]; then
        prompt="$prompt [$default]"
    fi

    if [ "$is_secret" = "true" ]; then
        read -sp "$prompt: " value
        echo ""
    else
        read -p "$prompt: " value
    fi

    if [ -z "$value" ] && [ -n "$default" ]; then
        value="$default"
    fi

    eval "$var_name='$value'"
}

prompt_yes_no() {
    local prompt="$1"
    local default="${2:-n}"

    if [ "$default" = "y" ]; then
        prompt="$prompt [Y/n]"
    else
        prompt="$prompt [y/N]"
    fi

    read -p "$prompt: " response
    response=${response:-$default}

    case "$response" in
        [yY]|[yY][eE][sS]) return 0 ;;
        *) return 1 ;;
    esac
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_error "This script must be run as root or with sudo"
        exit 1
    fi
}

################################################################################
# Step 1: Stop Existing Services and Free Ports
################################################################################

stop_existing_services() {
    print_header "Step 1: Stopping Existing Services"

    # Stop systemd service if exists
    if systemctl list-units --full -all | grep -Fq "mcp-rca.service"; then
        print_info "Stopping mcp-rca systemd service..."
        systemctl stop mcp-rca.service 2>/dev/null || true
        systemctl disable mcp-rca.service 2>/dev/null || true
        print_success "Systemd service stopped"
    fi

    # Stop supervisor if running
    if command -v supervisorctl &> /dev/null; then
        print_info "Stopping supervisor processes..."
        supervisorctl stop mcp-rca 2>/dev/null || true
        print_success "Supervisor stopped"
    fi

    # Kill any processes using our port
    print_info "Checking for processes on port ${PORT}..."
    if lsof -ti:${PORT} &> /dev/null; then
        print_warning "Killing processes on port ${PORT}..."
        lsof -ti:${PORT} | xargs kill -9 2>/dev/null || true
        sleep 2
        print_success "Port ${PORT} freed"
    else
        print_success "Port ${PORT} is available"
    fi

    # Kill any Python processes related to mcp-rca
    print_info "Checking for MCP-RCA processes..."
    if pgrep -f "mcp-rca" > /dev/null; then
        print_warning "Killing existing MCP-RCA processes..."
        pkill -9 -f "mcp-rca" 2>/dev/null || true
        sleep 2
        print_success "MCP-RCA processes terminated"
    fi

    print_success "All existing services stopped and ports freed"
    echo ""
}

################################################################################
# Step 2: Install System Dependencies
################################################################################

install_dependencies() {
    print_header "Step 2: Installing System Dependencies"

    # Detect OS
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        VERSION=$VERSION_ID
    else
        print_error "Cannot detect OS"
        exit 1
    fi

    print_info "Detected OS: $OS $VERSION"

    # Update package manager
    print_info "Updating package manager..."
    if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
        apt-get update -qq
    elif [ "$OS" = "amzn" ] || [ "$OS" = "rhel" ] || [ "$OS" = "centos" ]; then
        yum update -y -q
    fi

    # Install Python 3.10+
    print_info "Installing Python 3.10+..."
    if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
        apt-get install -y python3.10 python3.10-venv python3-pip git curl wget
    elif [ "$OS" = "amzn" ]; then
        yum install -y python3 python3-pip git curl wget
    fi

    # Verify Python version
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
    print_info "Python version: $PYTHON_VERSION"

    if (( $(echo "$PYTHON_VERSION < 3.10" | bc -l) )); then
        print_error "Python 3.10+ is required, found $PYTHON_VERSION"
        exit 1
    fi

    print_success "System dependencies installed"
    echo ""
}

################################################################################
# Step 3: Create Application User and Directories
################################################################################

setup_user_and_dirs() {
    print_header "Step 3: Creating User and Directories"

    # Create application user
    if ! id -u $APP_USER > /dev/null 2>&1; then
        print_info "Creating user: $APP_USER"
        useradd -r -m -s /bin/bash $APP_USER
        print_success "User created"
    else
        print_success "User already exists"
    fi

    # Create directories
    print_info "Creating directories..."
    mkdir -p $APP_DIR
    mkdir -p $LOG_DIR
    mkdir -p ${APP_DIR}/config
    mkdir -p ${APP_DIR}/credentials

    # Set permissions
    chown -R $APP_USER:$APP_USER $APP_DIR
    chown -R $APP_USER:$APP_USER $LOG_DIR
    chmod 750 ${APP_DIR}/credentials

    print_success "Directories created and permissions set"
    echo ""
}

################################################################################
# Step 4: Collect Credentials Interactively
################################################################################

collect_credentials() {
    print_header "Step 4: Collecting Credentials"

    echo ""
    print_info "This script will now collect all necessary credentials."
    print_info "You can configure support for GCP, AWS, Azure, or any combination."
    echo ""

    # Anthropic API Key (required)
    print_info "=== Anthropic API Key (Required) ==="
    echo "Get your API key from: https://console.anthropic.com/settings/keys"
    prompt_input "Enter Anthropic API Key" ANTHROPIC_API_KEY "" true

    if [ -z "$ANTHROPIC_API_KEY" ]; then
        print_error "Anthropic API Key is required"
        exit 1
    fi

    echo ""

    # GCP Configuration
    print_info "=== Google Cloud Platform (Optional) ==="
    if prompt_yes_no "Configure GCP monitoring?" "n"; then
        ENABLE_GCP="true"
        prompt_input "Enter GCP Project ID" GCP_PROJECT_ID

        print_info "You need to provide a GCP service account key JSON file."
        print_info "1. Go to: https://console.cloud.google.com/iam-admin/serviceaccounts"
        print_info "2. Create a service account with roles: Monitoring Viewer, Logging Viewer"
        print_info "3. Create and download a JSON key"
        echo ""
        prompt_input "Enter path to GCP service account JSON file" GCP_KEY_PATH

        if [ ! -f "$GCP_KEY_PATH" ]; then
            print_error "File not found: $GCP_KEY_PATH"
            exit 1
        fi

        # Copy key file to credentials directory
        cp "$GCP_KEY_PATH" "${APP_DIR}/credentials/gcp-key.json"
        chmod 600 "${APP_DIR}/credentials/gcp-key.json"
        chown $APP_USER:$APP_USER "${APP_DIR}/credentials/gcp-key.json"
        GCP_KEY_PATH="${APP_DIR}/credentials/gcp-key.json"

        print_success "GCP credentials configured"
    else
        ENABLE_GCP="false"
    fi

    echo ""

    # AWS Configuration
    print_info "=== Amazon Web Services (Optional) ==="
    if prompt_yes_no "Configure AWS monitoring?" "n"; then
        ENABLE_AWS="true"
        prompt_input "Enter AWS Region" AWS_REGION "us-east-1"

        print_info "AWS credentials can be configured via:"
        print_info "1. IAM Role (recommended for EC2)"
        print_info "2. Access Key / Secret Key"
        echo ""

        if prompt_yes_no "Use IAM Role (instance profile)?" "y"; then
            AWS_AUTH_METHOD="iam_role"
            print_success "Will use EC2 instance profile"
        else
            AWS_AUTH_METHOD="access_key"
            prompt_input "Enter AWS Access Key ID" AWS_ACCESS_KEY_ID
            prompt_input "Enter AWS Secret Access Key" AWS_SECRET_ACCESS_KEY "" true
        fi

        print_success "AWS credentials configured"
    else
        ENABLE_AWS="false"
    fi

    echo ""

    # Azure Configuration
    print_info "=== Microsoft Azure (Optional) ==="
    if prompt_yes_no "Configure Azure monitoring?" "n"; then
        ENABLE_AZURE="true"
        prompt_input "Enter Azure Subscription ID" AZURE_SUBSCRIPTION_ID
        prompt_input "Enter Azure Tenant ID" AZURE_TENANT_ID
        prompt_input "Enter Azure Client ID" AZURE_CLIENT_ID
        prompt_input "Enter Azure Client Secret" AZURE_CLIENT_SECRET "" true

        print_success "Azure credentials configured"
    else
        ENABLE_AZURE="false"
    fi

    echo ""

    # Project Configuration
    print_info "=== Project Configuration ==="
    prompt_input "Enter project name" PROJECT_NAME "my-project"
    prompt_input "Enter project display name" PROJECT_DISPLAY_NAME "$PROJECT_NAME"

    # Server Configuration
    print_info "=== Server Configuration ==="
    prompt_input "Enter server port" SERVER_PORT "8000"
    PORT=$SERVER_PORT

    print_success "All credentials collected"
    echo ""
}

################################################################################
# Step 5: Clone/Copy Application Code
################################################################################

setup_application() {
    print_header "Step 5: Setting Up Application"

    # Check if we're already in the repo
    if [ -d "$(pwd)/.git" ]; then
        print_info "Copying application from current directory..."
        cp -r "$(pwd)"/* $APP_DIR/
        cp -r "$(pwd)"/.git $APP_DIR/ 2>/dev/null || true
    else
        print_info "Cloning repository..."
        git clone https://github.com/akhanna222/mcp-rca.git $APP_DIR/
    fi

    # Set ownership
    chown -R $APP_USER:$APP_USER $APP_DIR

    print_success "Application code ready"
    echo ""
}

################################################################################
# Step 6: Create Virtual Environment and Install Dependencies
################################################################################

setup_python_env() {
    print_header "Step 6: Setting Up Python Environment"

    print_info "Creating virtual environment..."
    su - $APP_USER -c "cd $APP_DIR && python3 -m venv venv"

    print_info "Installing Python dependencies..."
    su - $APP_USER -c "cd $APP_DIR && source venv/bin/activate && pip install --upgrade pip setuptools wheel"
    su - $APP_USER -c "cd $APP_DIR && source venv/bin/activate && pip install -r requirements.txt"

    print_success "Python environment ready"
    echo ""
}

################################################################################
# Step 7: Create Configuration Files
################################################################################

create_config_files() {
    print_header "Step 7: Creating Configuration Files"

    # Create .env file
    print_info "Creating .env file..."
    cat > $ENV_FILE << EOF
# Anthropic API Configuration
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY

# GCP Configuration
$([ "$ENABLE_GCP" = "true" ] && echo "GOOGLE_APPLICATION_CREDENTIALS=$GCP_KEY_PATH" || echo "# GCP not configured")

# AWS Configuration
$([ "$ENABLE_AWS" = "true" ] && echo "AWS_REGION=$AWS_REGION" || echo "# AWS not configured")
$([ "$ENABLE_AWS" = "true" ] && [ "$AWS_AUTH_METHOD" = "access_key" ] && echo "AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID" || echo "")
$([ "$ENABLE_AWS" = "true" ] && [ "$AWS_AUTH_METHOD" = "access_key" ] && echo "AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY" || echo "")

# Azure Configuration
$([ "$ENABLE_AZURE" = "true" ] && echo "AZURE_SUBSCRIPTION_ID=$AZURE_SUBSCRIPTION_ID" || echo "# Azure not configured")
$([ "$ENABLE_AZURE" = "true" ] && echo "AZURE_TENANT_ID=$AZURE_TENANT_ID" || echo "")
$([ "$ENABLE_AZURE" = "true" ] && echo "AZURE_CLIENT_ID=$AZURE_CLIENT_ID" || echo "")
$([ "$ENABLE_AZURE" = "true" ] && echo "AZURE_CLIENT_SECRET=$AZURE_CLIENT_SECRET" || echo "")
EOF

    chmod 600 $ENV_FILE
    chown $APP_USER:$APP_USER $ENV_FILE

    # Create platform.yaml
    print_info "Creating platform configuration..."

    # Determine cloud provider
    if [ "$ENABLE_GCP" = "true" ]; then
        PROVIDER="gcp"
    elif [ "$ENABLE_AWS" = "true" ]; then
        PROVIDER="aws"
    elif [ "$ENABLE_AZURE" = "true" ]; then
        PROVIDER="azure"
    else
        print_error "At least one cloud provider must be configured"
        exit 1
    fi

    cat > $CONFIG_FILE << EOF
# MCP-RCA Platform Configuration
# Generated by setup_ec2.sh on $(date)

platform:
  name: "MCP-RCA Platform"
  version: "1.0.0"
  environment: "production"

anthropic:
  api_key_env: "ANTHROPIC_API_KEY"
  model: "claude-3-7-sonnet-20250219"
  max_tokens: 16000
  temperature: 0.0

server:
  host: "0.0.0.0"
  port: $PORT
  webhook_path: "/webhook"

alerts:
  timeout_seconds: 120
  max_concurrent_alerts: 10
  retry_attempts: 3
  retry_delay_seconds: 5

logging:
  level: "INFO"
  format: "json"
  file: "$LOG_DIR/mcp-rca.log"
  max_bytes: 10485760  # 10MB
  backup_count: 5

projects:
  - name: "$PROJECT_NAME"
    display_name: "$PROJECT_DISPLAY_NAME"
    provider: "$PROVIDER"
    enabled: true
EOF

    # Add GCP config if enabled
    if [ "$ENABLE_GCP" = "true" ]; then
        cat >> $CONFIG_FILE << EOF
    gcp:
      project_id: "$GCP_PROJECT_ID"
      credentials_path_env: "GOOGLE_APPLICATION_CREDENTIALS"
      metrics:
        enabled: true
      logging:
        enabled: true
      monitoring_query_defaults:
        alignment_period: "60s"
        per_series_aligner: "ALIGN_MEAN"
EOF
    fi

    # Add AWS config if enabled
    if [ "$ENABLE_AWS" = "true" ]; then
        cat >> $CONFIG_FILE << EOF
    aws:
      region_env: "AWS_REGION"
      $([ "$AWS_AUTH_METHOD" = "access_key" ] && echo "access_key_id_env: \"AWS_ACCESS_KEY_ID\"" || echo "# Using IAM role")
      $([ "$AWS_AUTH_METHOD" = "access_key" ] && echo "secret_access_key_env: \"AWS_SECRET_ACCESS_KEY\"" || echo "")
      cloudwatch:
        enabled: true
      cloudwatch_logs:
        enabled: true
EOF
    fi

    # Add Azure config if enabled
    if [ "$ENABLE_AZURE" = "true" ]; then
        cat >> $CONFIG_FILE << EOF
    azure:
      subscription_id_env: "AZURE_SUBSCRIPTION_ID"
      tenant_id_env: "AZURE_TENANT_ID"
      client_id_env: "AZURE_CLIENT_ID"
      client_secret_env: "AZURE_CLIENT_SECRET"
      monitor:
        enabled: true
      log_analytics:
        enabled: true
EOF
    fi

    chown $APP_USER:$APP_USER $CONFIG_FILE
    chmod 640 $CONFIG_FILE

    print_success "Configuration files created"
    echo ""
}

################################################################################
# Step 8: Validate Configuration
################################################################################

validate_configuration() {
    print_header "Step 8: Validating Configuration"

    print_info "Running configuration validation..."
    su - $APP_USER -c "cd $APP_DIR && source venv/bin/activate && python src/cli.py validate --config $CONFIG_FILE"

    print_success "Configuration validated successfully"
    echo ""
}

################################################################################
# Step 9: Create Systemd Service
################################################################################

create_systemd_service() {
    print_header "Step 9: Creating Systemd Service"

    print_info "Creating systemd service file..."
    cat > /etc/systemd/system/mcp-rca.service << EOF
[Unit]
Description=MCP-RCA Platform - AI-Powered Root Cause Analysis
After=network.target
Documentation=https://github.com/akhanna222/mcp-rca

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=$ENV_FILE
ExecStart=$APP_DIR/venv/bin/python src/api/server.py --config $CONFIG_FILE
Restart=always
RestartSec=10
StandardOutput=append:$LOG_DIR/mcp-rca.log
StandardError=append:$LOG_DIR/mcp-rca-error.log

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$LOG_DIR $APP_DIR/config

# Resource limits
LimitNOFILE=65536
LimitNPROC=4096

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd
    systemctl daemon-reload

    # Enable service
    systemctl enable mcp-rca.service

    print_success "Systemd service created and enabled"
    echo ""
}

################################################################################
# Step 10: Configure Firewall
################################################################################

configure_firewall() {
    print_header "Step 10: Configuring Firewall"

    if command -v ufw &> /dev/null; then
        print_info "Configuring UFW firewall..."
        ufw allow $PORT/tcp comment "MCP-RCA Platform"
        print_success "Firewall rule added for port $PORT"
    elif command -v firewall-cmd &> /dev/null; then
        print_info "Configuring firewalld..."
        firewall-cmd --permanent --add-port=$PORT/tcp
        firewall-cmd --reload
        print_success "Firewall rule added for port $PORT"
    else
        print_warning "No firewall detected. Please manually open port $PORT"
    fi

    echo ""
}

################################################################################
# Step 11: Start Service
################################################################################

start_service() {
    print_header "Step 11: Starting Service"

    print_info "Starting MCP-RCA service..."
    systemctl start mcp-rca.service

    # Wait for service to start
    sleep 3

    # Check status
    if systemctl is-active --quiet mcp-rca.service; then
        print_success "Service started successfully"
    else
        print_error "Service failed to start"
        print_info "Check logs: journalctl -u mcp-rca.service -n 50"
        exit 1
    fi

    echo ""
}

################################################################################
# Step 12: Health Check
################################################################################

perform_health_check() {
    print_header "Step 12: Health Check"

    print_info "Waiting for service to be ready..."
    sleep 5

    print_info "Testing health endpoint..."
    if curl -s http://localhost:$PORT/health > /dev/null; then
        print_success "Health check passed"

        # Get health details
        HEALTH=$(curl -s http://localhost:$PORT/health)
        echo ""
        print_info "Service Details:"
        echo "$HEALTH" | python3 -m json.tool
    else
        print_warning "Health check failed - service may still be starting"
        print_info "Check status: systemctl status mcp-rca.service"
    fi

    echo ""
}

################################################################################
# Step 13: Print Summary
################################################################################

print_summary() {
    print_header "Installation Complete!"

    echo ""
    print_success "MCP-RCA Platform has been successfully installed and started"
    echo ""

    print_info "Service Information:"
    echo "  • Status: $(systemctl is-active mcp-rca.service)"
    echo "  • Port: $PORT"
    echo "  • Config: $CONFIG_FILE"
    echo "  • Logs: $LOG_DIR/mcp-rca.log"
    echo ""

    print_info "Webhook URL (for alerts):"
    echo "  http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || hostname -I | awk '{print $1}'):$PORT/webhook"
    echo ""

    print_info "Useful Commands:"
    echo "  • Check status:   systemctl status mcp-rca.service"
    echo "  • View logs:      journalctl -u mcp-rca.service -f"
    echo "  • Restart:        systemctl restart mcp-rca.service"
    echo "  • Stop:           systemctl stop mcp-rca.service"
    echo "  • Health check:   curl http://localhost:$PORT/health"
    echo ""

    print_info "Next Steps:"
    echo "  1. Configure your monitoring system to send alerts to the webhook URL"
    echo "  2. Test with a sample alert: curl -X POST http://localhost:$PORT/webhook -H 'Content-Type: application/json' -d '{...}'"
    echo "  3. Monitor logs for incoming alerts and RCA results"
    echo ""

    if [ "$ENABLE_GCP" = "true" ]; then
        print_info "GCP Configuration:"
        echo "  • Project: $GCP_PROJECT_ID"
        echo "  • Enable Cloud Monitoring API: https://console.cloud.google.com/apis/library/monitoring.googleapis.com"
        echo "  • Configure alert webhook in Notification Channels"
        echo ""
    fi

    if [ "$ENABLE_AWS" = "true" ]; then
        print_info "AWS Configuration:"
        echo "  • Region: $AWS_REGION"
        echo "  • Configure SNS topic to send to webhook URL"
        echo ""
    fi

    if [ "$ENABLE_AZURE" = "true" ]; then
        print_info "Azure Configuration:"
        echo "  • Subscription: $AZURE_SUBSCRIPTION_ID"
        echo "  • Configure Action Group with webhook"
        echo ""
    fi

    print_warning "Security Recommendations:"
    echo "  • Set up HTTPS with a reverse proxy (Nginx + Let's Encrypt)"
    echo "  • Configure authentication for webhook endpoint"
    echo "  • Restrict firewall rules to known monitoring IPs"
    echo "  • Regularly rotate credentials"
    echo ""

    print_success "Installation log saved to: /var/log/mcp-rca-setup.log"
    echo ""
}

################################################################################
# Main Execution
################################################################################

main() {
    # Banner
    clear
    echo ""
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║                                                            ║"
    echo "║            MCP-RCA Platform - EC2 Setup Script            ║"
    echo "║                                                            ║"
    echo "║         AI-Powered Root Cause Analysis Platform           ║"
    echo "║                                                            ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""

    # Check root
    check_root

    # Confirm
    if ! prompt_yes_no "This will set up MCP-RCA Platform. Continue?" "y"; then
        echo "Setup cancelled"
        exit 0
    fi

    echo ""

    # Execute setup steps
    stop_existing_services
    install_dependencies
    setup_user_and_dirs
    collect_credentials
    setup_application
    setup_python_env
    create_config_files
    validate_configuration
    create_systemd_service
    configure_firewall
    start_service
    perform_health_check
    print_summary
}

# Run main function and log everything
main 2>&1 | tee /var/log/mcp-rca-setup.log

exit 0
