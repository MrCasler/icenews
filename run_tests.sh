#!/bin/bash
# Test runner for ICENews
# Run this script before deploying to verify all tests pass

set -e  # Exit on any error

echo "======================================"
echo "ICENews Test Suite"
echo "======================================"
echo ""

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Run all tests
echo "Running all tests..."
python -m pytest tests/ -v --tb=short

echo ""
echo "======================================"
echo "✓ All tests passed!"
echo "======================================"
echo ""
echo "Test summary:"
echo "  - Security tests: SQL injection, XSS, input validation"
echo "  - Smoke tests: Homepage, API, likes, health check"
echo "  - Basic auth tests: Password gate (auth disabled tests only)"
echo "  - Database integrity: Tables and schema"
echo ""
echo "Note: Auth-enabled tests are skipped (run separately with credentials)"
echo ""
echo "Ready for deployment."
