#!/bin/bash
################################################################################
# MCP-RCA Platform - Port Cleanup Script
#
# This script stops all MCP-RCA services and frees ports.
# Run this before starting fresh or if services are stuck.
#
# Usage:
#   sudo bash scripts/cleanup_ports.sh [PORT]
#
# Default port: 8000
################################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PORT=${1:-8000}

echo -e "${GREEN}╔════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   MCP-RCA Port Cleanup & Service Stop    ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}✗ This script must be run as root or with sudo${NC}"
    exit 1
fi

echo -e "${YELLOW}→ Stopping services and freeing port ${PORT}...${NC}"
echo ""

# Stop systemd service
if systemctl list-units --full -all | grep -Fq "mcp-rca.service"; then
    echo "Stopping systemd service..."
    systemctl stop mcp-rca.service 2>/dev/null || true
    echo -e "${GREEN}✓ Systemd service stopped${NC}"
fi

# Stop supervisor
if command -v supervisorctl &> /dev/null; then
    if supervisorctl status mcp-rca 2>/dev/null | grep -q "RUNNING"; then
        echo "Stopping supervisor process..."
        supervisorctl stop mcp-rca 2>/dev/null || true
        echo -e "${GREEN}✓ Supervisor process stopped${NC}"
    fi
fi

# Kill processes on specific port
echo "Checking port ${PORT}..."
if lsof -ti:${PORT} &> /dev/null; then
    echo "Killing processes on port ${PORT}..."
    lsof -ti:${PORT} | xargs kill -9 2>/dev/null || true
    sleep 2
    echo -e "${GREEN}✓ Port ${PORT} freed${NC}"
else
    echo -e "${GREEN}✓ Port ${PORT} already free${NC}"
fi

# Kill any MCP-RCA Python processes
echo "Checking for MCP-RCA processes..."
if pgrep -f "mcp-rca" > /dev/null 2>&1; then
    echo "Killing MCP-RCA processes..."
    pkill -9 -f "mcp-rca" 2>/dev/null || true
    sleep 1
    echo -e "${GREEN}✓ MCP-RCA processes terminated${NC}"
else
    echo -e "${GREEN}✓ No MCP-RCA processes running${NC}"
fi

# Kill any Python processes running MCP servers
echo "Checking for MCP server processes..."
if pgrep -f "mcp_servers" > /dev/null 2>&1; then
    echo "Killing MCP server processes..."
    pkill -9 -f "mcp_servers" 2>/dev/null || true
    sleep 1
    echo -e "${GREEN}✓ MCP server processes terminated${NC}"
else
    echo -e "${GREEN}✓ No MCP server processes running${NC}"
fi

# Check for any remaining processes
echo ""
echo "Final process check..."
REMAINING=$(ps aux | grep -E "(mcp-rca|mcp_servers)" | grep -v grep | wc -l)

if [ "$REMAINING" -gt 0 ]; then
    echo -e "${YELLOW}⚠ Warning: ${REMAINING} related processes still running${NC}"
    echo "Showing remaining processes:"
    ps aux | grep -E "(mcp-rca|mcp_servers)" | grep -v grep
else
    echo -e "${GREEN}✓ All processes cleaned up${NC}"
fi

# Final port check
echo ""
echo "Final port check..."
if lsof -ti:${PORT} &> /dev/null; then
    echo -e "${RED}✗ Port ${PORT} still in use by:${NC}"
    lsof -i:${PORT}
    exit 1
else
    echo -e "${GREEN}✓ Port ${PORT} is free${NC}"
fi

echo ""
echo -e "${GREEN}✓ Cleanup complete!${NC}"
echo ""
echo "You can now start the service with:"
echo "  systemctl start mcp-rca.service"
echo "  or"
echo "  sudo bash scripts/setup_ec2.sh"
echo ""

exit 0
