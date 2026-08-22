#!/bin/bash

# CyberEpi Deployment Preparation Script
# This script helps prepare the project for deployment on various platforms

set -e

echo "🚀 Preparing CyberEpi for deployment..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if we're in the right directory
if [ ! -f "README.md" ] || [ ! -d "services" ]; then
    echo "❌ Please run this script from the CyberEpi root directory"
    exit 1
fi

# Create necessary directories
echo "📁 Creating deployment directories..."
mkdir -p deploy/free
mkdir -p deploy/prod

# Generate random passwords
echo "🔐 Generating secure passwords..."
POSTGRES_PASSWORD=$(openssl rand -base64 32)

# Create .env.production template
echo "📝 Creating .env.production template..."
cat > .env.production << EOF
# Database Configuration
DATABASE_URL=postgresql+asyncpg://cyberepi:${POSTGRES_PASSWORD}@HOST:5432/cyberepi
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}

# Redis Configuration
REDIS_URL=redis://HOST:6379/0

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS=HOST:9092

# Keycloak Configuration
KEYCLOAK_URL=https://your-keycloak-url.com
KEYCLOAK_REALM=cyberepi

# Service Ports
SERVICE_PORT_USER=8001
SERVICE_PORT_SYMPTOM=8002
SERVICE_PORT_PRESCRIPTION=8003
SERVICE_PORT_NOTIFICATION=8004
SERVICE_PORT_EPI=8005
SERVICE_PORT_PRIVACY=8006

# External APIs
OPENFDA_API_URL=https://api.fda.gov
RXNORM_API_URL=https://rxnav.nlm.nih.gov/REST

# Logging
LOG_LEVEL=INFO
EOF

echo "✅ Created .env.production with secure credentials"
echo "⚠️  Remember to update HOST values with your actual service URLs"

# Build all Docker images
echo "🐳 Building Docker images..."
services=("user-service" "symptom-service" "prescription-service" "notification-service" "epi-engine" "privacy-service")

for service in "${services[@]}"; do
    echo "Building ${service}..."
    cd services/${service}
    docker build -t cyberepi/${service}:latest .
    cd ../..
done

# Create deployment registry info
echo "📋 Creating deployment registry info..."
cat > deploy/REGISTRY_INFO.md << EOF
# Docker Registry Information

## Local Images
The following images have been built locally:
EOF

for service in "${services[@]}"; do
    echo "- cyberepi/${service}:latest" >> deploy/REGISTRY_INFO.md
done

cat >> deploy/REGISTRY_INFO.md << EOF

## Push to Registry

### Docker Hub
```bash
docker login
docker push cyberepi/user-service:latest
docker push cyberepi/symptom-service:latest
docker push cyberepi/prescription-service:latest
docker push cyberepi/notification-service:latest
docker push cyberepi/epi-engine:latest
docker push cyberepi/privacy-service:latest
```

### GitHub Container Registry
```bash
docker tag cyberepi/user-service:latest ghcr.io/yourusername/cyberepi-user-service:latest
docker tag cyberepi/symptom-service:latest ghcr.io/yourusername/cyberepi-symptom-service:latest
# ... repeat for all services

docker login ghcr.io
docker push ghcr.io/yourusername/cyberepi-user-service:latest
# ... repeat for all services
```
EOF

# Platform-specific setup
echo "🔧 Setting up platform-specific configurations..."

# Render setup
echo "📦 Preparing Render configuration..."
cp deploy/free/render.yaml render.yaml 2>/dev/null || echo "render.yaml already exists or not needed"

# Railway setup
echo "🚂 Preparing Railway configuration..."
cp deploy/free/railway.toml railway.toml 2>/dev/null || echo "railway.toml already exists or not needed"

# Create deployment checklist
echo "✅ Creating deployment checklist..."
cat > deploy/CHECKLIST.md << EOF
# Deployment Checklist

## Pre-Deployment
- [ ] All Docker images built successfully
- [ ] Environment variables configured
- [ ] Database migration scripts ready
- [ ] SSL certificates configured (if needed)
- [ ] Domain names configured (if using custom domains)

## Platform-Specific
- [ ] Render: render.yaml configured
- [ ] Railway: railway.toml configured
- [ ] Fly.io: fly.toml configured
- [ ] Vercel: vercel.json configured
- [ ] Kubernetes: manifests reviewed

## Post-Deployment
- [ ] Health checks passing
- [ ] Database connected
- [ ] Services communicating
- [ ] Monitoring configured
- [ ] Backup strategy in place
- [ ] Log aggregation working

## Security
- [ ] Default passwords changed
- [ ] HTTPS enabled
- [ ] CORS configured
- [ ] Rate limiting enabled
- [ ] Audit logging enabled
EOF

echo ""
echo "🎉 Deployment preparation complete!"
echo ""
echo "Next steps:"
echo "1. Review .env.production and update HOST values"
echo "2. Choose your deployment platform"
echo "3. Follow the platform-specific guide in DEPLOYMENT.md"
echo "4. Run through the checklist in deploy/CHECKLIST.md"
echo ""
echo "📖 For detailed deployment instructions, see: DEPLOYMENT.md"
