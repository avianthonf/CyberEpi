# CyberEpi Backend Services Startup Script
# This script builds and starts all microservices

Write-Host "=== CyberEpi Backend Services Setup ===" -ForegroundColor Green

# Stop and remove existing containers
Write-Host "`n1. Cleaning up existing containers..." -ForegroundColor Yellow
docker stop $(docker ps -q --filter "name=cyberepi-*") 2>$null
docker rm $(docker ps -aq --filter "name=cyberepi-*") 2>$null

# Build all service images
Write-Host "`n2. Building service images..." -ForegroundColor Yellow
$services = @("user-service", "symptom-service", "prescription-service", "notification-service", "epi-engine", "privacy-service")

foreach ($service in $services) {
    Write-Host "Building $service..." -ForegroundColor Cyan
    Set-Location "services\$service"
    docker build -t cyberepi/$service`:latest .
    Set-Location ..\..
}

# Start infrastructure services (if not running)
Write-Host "`n3. Starting infrastructure services..." -ForegroundColor Yellow
Set-Location infra
docker-compose -f docker-compose.infra.yml up -d

# Wait for infrastructure to be healthy
Write-Host "`n4. Waiting for infrastructure services to be healthy..." -ForegroundColor Yellow
do {
    Start-Sleep 5
    $healthy = docker-compose -f docker-compose.infra.yml ps --format "table {{.Service}}\t{{.Status}}" | Select-String "healthy"
    Write-Host "Infrastructure services ready: $($healthy.Count)" -ForegroundColor Gray
} while ($healthy.Count -lt 5)

# Start Kong API Gateway
Write-Host "`n5. Starting Kong API Gateway..." -ForegroundColor Yellow
docker-compose up -d kong

# Start all microservices
Write-Host "`n6. Starting microservices..." -ForegroundColor Yellow

$envVars = @{
    "user-service" = @{
        port = "8011:8001"
        env = @(
            "DATABASE_URL=postgresql+asyncpg://cyberepi:devpassword@postgres:5432/cyberepi",
            "REDIS_URL=redis://redis:6379/0",
            "KEYCLOAK_URL=http://keycloak:8080",
            "JWT_SECRET_KEY=dev-secret-key"
        )
    }
    "symptom-service" = @{
        port = "8012:8002"
        env = @(
            "DATABASE_URL=postgresql+asyncpg://cyberepi:devpassword@postgres:5432/cyberepi",
            "REDIS_URL=redis://redis:6379/0",
            "KAFKA_BOOTSTRAP_SERVERS=kafka:9092"
        )
    }
    "prescription-service" = @{
        port = "8013:8003"
        env = @(
            "DATABASE_URL=postgresql+asyncpg://cyberepi:devpassword@postgres:5432/cyberepi",
            "REDIS_URL=redis://redis:6379/0"
        )
    }
    "notification-service" = @{
        port = "8014:8004"
        env = @(
            "DATABASE_URL=postgresql+asyncpg://cyberepi:devpassword@postgres:5432/cyberepi",
            "REDIS_URL=redis://redis:6379/0",
            "KAFKA_BOOTSTRAP_SERVERS=kafka:9092"
        )
    }
    "epi-engine" = @{
        port = "8015:8005"
        env = @(
            "DATABASE_URL=postgresql+asyncpg://cyberepi:devpassword@postgres:5432/cyberepi",
            "REDIS_URL=redis://redis:6379/0",
            "KAFKA_BOOTSTRAP_SERVERS=kafka:9092"
        )
    }
    "privacy-service" = @{
        port = "8016:8006"
        env = @(
            "DATABASE_URL=postgresql+asyncpg://cyberepi:devpassword@postgres:5432/cyberepi",
            "REDIS_URL=redis://redis:6379/0"
        )
    }
}

foreach ($service in $services) {
    Write-Host "Starting $service on port $($envVars[$service].port)..." -ForegroundColor Cyan
    # Build docker args: each env var as a separate "-e" pair (PowerShell < 7.3
    # does not expand arrays into native command args automatically).
    $dockerArgs = @("-d", "--name", "cyberepi-$service", "--network", "cyberepi-net", "-p", $envVars[$service].port)
    foreach ($envVar in $envVars[$service].env) {
        $dockerArgs += @("-e", $envVar)
    }
    $dockerArgs += "cyberepi/$service`:latest"
    docker run @dockerArgs
}

# Check status
Write-Host "`n7. Checking service status..." -ForegroundColor Yellow
Start-Sleep 10
docker ps --filter "name=cyberepi-*" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

Write-Host "`n=== Backend services startup complete! ===" -ForegroundColor Green
Write-Host "`nAPI Gateway: http://localhost:8000" -ForegroundColor White
Write-Host "Keycloak Admin: http://localhost:8080 (admin/admin)" -ForegroundColor White
Write-Host "`nTo view logs: docker logs -f cyberepi-[service-name]" -ForegroundColor Gray

Set-Location ..
