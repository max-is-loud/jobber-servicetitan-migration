#!/bin/bash
# OAuth Hang Fix Manual Validation Protocol
# 
# This script validates that the OAuth hang fix is working correctly by:
# 1. Setting up a clean test environment
# 2. Running the OAuth init command with timing measurement
# 3. Providing clear success/failure criteria and feedback
#
# Expected behavior: OAuth init should complete within 10 seconds after
# browser authorization and exit cleanly with code 0.

set -e  # Exit on any error

# Colors for output formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
TEST_DB_NAME="test_oauth_hang_fix.db"
MAX_EXPECTED_DURATION=10  # seconds after authorization
TIMEOUT_DURATION=300     # 5 minutes maximum for entire process

echo -e "${BLUE}OAuth Hang Fix Manual Validation Protocol${NC}"
echo -e "${BLUE}===========================================${NC}"
echo ""

# Function to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}Cleaning up...${NC}"
    # Kill any hanging processes if needed
    pkill -f "tightbeam oauth init" 2>/dev/null || true
    # Remove test database
    rm -f "$TEST_DB_NAME" 2>/dev/null || true
}

# Set trap for cleanup on script exit
trap cleanup EXIT

# Step 1: Environment verification
echo -e "${BLUE}Step 1: Verifying environment...${NC}"
if ! command -v poetry &> /dev/null; then
    echo -e "${RED}❌ ERROR: Poetry not found. Please install Poetry first.${NC}"
    exit 1
fi

if [ ! -f "pyproject.toml" ]; then
    echo -e "${RED}❌ ERROR: Not in TightBeam project directory. Please run from project root.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Environment verified${NC}"
echo ""

# Step 2: Clean database setup
echo -e "${BLUE}Step 2: Setting up clean test environment...${NC}"
if [ -f "$TEST_DB_NAME" ]; then
    echo -e "${YELLOW}Removing existing test database: $TEST_DB_NAME${NC}"
    rm -f "$TEST_DB_NAME"
fi

echo -e "${GREEN}✅ Clean test environment ready${NC}"
echo ""

# Step 3: Pre-execution instructions
echo -e "${BLUE}Step 3: Manual validation instructions${NC}"
echo -e "${YELLOW}IMPORTANT: This test requires manual interaction${NC}"
echo ""
echo "The OAuth init command will:"
echo "1. Display authorization URL"
echo "2. Open your browser (if possible)"
echo "3. Wait for you to authorize the application"
echo "4. Complete the OAuth flow"
echo ""
echo -e "${YELLOW}Expected behavior after authorization:${NC}"
echo "• Command should complete within ${MAX_EXPECTED_DURATION} seconds"
echo "• Process should exit cleanly with code 0"
echo "• No manual interruption (Ctrl+C) should be needed"
echo "• Success message should be displayed"
echo ""
echo -e "${YELLOW}Please be ready to authorize in your browser when prompted.${NC}"
echo ""
read -p "Press Enter when ready to proceed with OAuth init test..."

# Step 4: Execute OAuth init with timing
echo -e "\n${BLUE}Step 4: Running OAuth init command...${NC}"
echo -e "${BLUE}Command: poetry run tightbeam oauth init --auto --db ./$TEST_DB_NAME${NC}"
echo ""

# Record start time
start_time=$(date +%s)

# Run the command with timeout protection
echo -e "${YELLOW}Starting OAuth init (timeout: ${TIMEOUT_DURATION}s)...${NC}"
if timeout $TIMEOUT_DURATION poetry run tightbeam oauth init --auto --db "./$TEST_DB_NAME"; then
    exit_code=0
else
    exit_code=$?
fi

# Record end time
end_time=$(date +%s)
duration=$((end_time - start_time))

# Step 5: Results analysis
echo ""
echo -e "${BLUE}=== VALIDATION RESULTS ===${NC}"
echo "Exit code: $exit_code"
echo "Total duration: ${duration} seconds"
echo "Expected: Exit code 0, Duration < ${MAX_EXPECTED_DURATION} seconds after authorization"
echo ""

# Detailed analysis
success=true

# Check exit code
if [ $exit_code -eq 0 ]; then
    echo -e "${GREEN}✅ Exit code check: PASSED (exit code 0)${NC}"
else
    echo -e "${RED}❌ Exit code check: FAILED (exit code $exit_code)${NC}"
    success=false
fi

# Check timing (note: this includes authorization time, so we're more lenient)
if [ $duration -lt 60 ]; then  # 1 minute is reasonable including user authorization time
    echo -e "${GREEN}✅ Timing check: PASSED (${duration}s - reasonable including authorization)${NC}"
elif [ $duration -lt 120 ]; then  # 2 minutes is acceptable
    echo -e "${YELLOW}⚠️  Timing check: ACCEPTABLE (${duration}s - within acceptable range)${NC}"
else
    echo -e "${RED}❌ Timing check: FAILED (${duration}s - too long, may indicate hanging)${NC}"
    success=false
fi

# Check if database was created (indicates successful completion)
if [ -f "$TEST_DB_NAME" ]; then
    echo -e "${GREEN}✅ Database creation: PASSED (OAuth tokens stored)${NC}"
else
    echo -e "${RED}❌ Database creation: FAILED (no tokens stored)${NC}"
    success=false
fi

# Check for timeout
if [ $exit_code -eq 124 ]; then
    echo -e "${RED}❌ Process timeout: FAILED (command timed out after ${TIMEOUT_DURATION}s)${NC}"
    success=false
fi

echo ""

# Final verdict
if [ "$success" = true ]; then
    echo -e "${GREEN}🎉 OVERALL RESULT: SUCCESS${NC}"
    echo -e "${GREEN}✅ OAuth hang fix is working correctly!${NC}"
    echo ""
    echo "The OAuth init command:"
    echo "• Completed successfully with exit code 0"
    echo "• Did not hang after authentication"
    echo "• Stored tokens in the database"
    echo "• Exited cleanly without manual intervention"
    exit 0
else
    echo -e "${RED}💥 OVERALL RESULT: FAILURE${NC}"
    echo -e "${RED}❌ OAuth hang fix validation failed!${NC}"
    echo ""
    echo "Issues detected:"
    [ $exit_code -ne 0 ] && echo "• Non-zero exit code ($exit_code)"
    [ $duration -ge 120 ] && echo "• Excessive duration (${duration}s)"
    [ ! -f "$TEST_DB_NAME" ] && echo "• No database created"
    [ $exit_code -eq 124 ] && echo "• Process timeout"
    echo ""
    echo "Please check the OAuth hang fix implementation."
    exit 1
fi 