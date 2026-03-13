# CyberEpi Deployment Preparation Script (PowerShell)
# This script helps prepare the project for deployment on various platforms

param(
    [switch]$SkipDockerBuild
)

Write-Host "🚀 Preparing CyberEpi for deployment..." -ForegroundColor Green

# Check if Docker is installed
try {
    docker --version | Out-Null
} catch {
    Write-Host "❌ Docker is not installed. Please install Docker Desktop first." -ForegroundColor Red
    exit 1
}

# Check if we're in the right directory
if (-not (Test-Path "README.md") -or -not (Test-Path "services")) {
    Write-Host "❌ Please run this script from the CyberEpi root directory" -ForegroundColor Red
    exit 1
}

# Create necessary directories
Write-Host "📁 Creating deployment directories..." -ForegroundColor Blue
New-Item -ItemType Directory -Force -Path "deploy\free" | Out-Null
New-Item -ItemType Directory -Force -Path "deploy\prod" | Out-Null

# Generate random passwords
Write-Host "🔐 Generating secure passwords..." -ForegroundColor Blue
$postgresPassword = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
$jwtSecret = -join ((48..57) + (65..90) + (97..122) + (33..47) | Get-Random -Count 64 | ForEach-Object {[char]$_})
$encryptionKey = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})

# Create .env.production template
Write-Host "📝 Creating .env.production template..." -ForegroundColor Blue
$envContent = @"
# Database Configuration
DATABASE_URL=postgresql://cyberepi:${postgresPassword}@HOST:5432/cyberepi
POSTGRES_PASSWORD=${postgresPassword}

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

# Security Keys
JWT_SECRET_KEY=${jwtSecret}
ENCRYPTION_KEY=${encryptionKey}

# External APIs
OPENFDA_API_URL=https://api.fda.gov
RXNORM_API_URL=https://rxnav.nlm.nih.gov/REST

# Logging
LOG_LEVEL=INFO
"@

Set-Content -Path ".env.production" -Value $envContent -Encoding UTF8
Write-Host "✅ Created .env.production with secure credentials" -ForegroundColor Green
Write-Host "⚠️  Remember to update HOST values with your actual service URLs" -ForegroundColor Yellow

# Build all Docker images
if (-not $SkipDockerBuild) {
    Write-Host "🐳 Building Docker images..." -ForegroundColor Blue
    $services = @("user-service", "symptom-service", "prescription-service", "notification-service", "epi-engine", "privacy-service")
    
    foreach ($service in $services) {
        Write-Host "Building ${service}..." -ForegroundColor Cyan
        Set-Location "services\$service"
        docker build -t "cyberepi/${service}:latest" .
        Set-Location "..\.."
    }
}

# Create deployment registry info
Write-Host "📋 Creating deployment registry info..." -ForegroundColor Blue
$registryContent = @"
# Docker Registry Information

## Local Images
The following images have been built locally:
"@

if (-not $SkipDockerBuild) {
    foreach ($service in $services) {
        $registryContent += "`n- cyberepi/${service}:latest"
    }
}

$registryContent += @"

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
"@

Set-Content -Path "deploy\REGISTRY_INFO.md" -Value $registryContent -Encoding UTF8

# Platform-specific setup
Write-Host "🔧 Setting up platform-specific configurations..." -ForegroundColor Blue

# Render setup
if (Test-Path "deploy\free\render.yaml") {
    Copy-Item "deploy\free\render.yaml" "render.yaml" -ErrorAction SilentlyContinue
    Write-Host "📦 Render configuration ready" -ForegroundColor Green
}

# Railway setup
if (Test-Path "deploy\free\railway.toml") {
    Copy-Item "deploy\free\railway.toml" "railway.toml" -ErrorAction SilentlyContinue
    Write-Host "🚂 Railway configuration ready" -ForegroundColor Green
}

# Create deployment checklist
Write-Host "✅ Creating deployment checklist..." -ForegroundColor Blue
$checklistContent = @"
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
"@

Set-Content -Path "deploy\CHECKLIST.md" -Value $checklistContent -Encoding UTF8

Write-Host ""
Write-Host "🎉 Deployment preparation complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Review .env.production and update HOST values" -ForegroundColor White
Write-Host "2. Choose your deployment platform" -ForegroundColor White
Write-Host "3. Follow the platform-specific guide in DEPLOYMENT.md" -ForegroundColor White
Write-Host "4. Run through the checklist in deploy\CHECKLIST.md" -ForegroundColor White
Write-Host ""
Write-Host "📖 For detailed deployment instructions, see: DEPLOYMENT.md" -ForegroundColor Cyan
