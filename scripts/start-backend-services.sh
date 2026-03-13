#!/bin/bash
# CyberEpi Backend Services Startup Script
# This script builds and starts all microservices

set -e

echo "=== CyberEpi Backend Services Setup ==="

# Stop and remove existing containers
echo -e "\n1. Cleaning up existing containers..."
docker stop $(docker ps -q --filter "name=cyberepi-*") 2>/dev/null || true
docker rm $(docker ps -aq --filter "name=cyberepi-*") 2>/dev/null || true

# Build all service images
echo -e "\n2. Building service images..."
services=("user-service" "symptom-service" "prescription-service" "notification-service" "epi-engine" "privacy-service")

for service in "${services[@]}"; do
    echo "Building $service..."
    cd "services/$service"
    docker build -t cyberepi/$service:latest .
    cd ../..
done

# Start infrastructure services (if not running)
echo -e "\n3. Starting infrastructure services..."
cd infra
docker-compose -f docker-compose.infra.yml up -d

# Wait for infrastructure to be healthy
echo -e "\n4. Waiting for infrastructure services to be healthy..."
while [ $(docker-compose -f docker-compose.infra.yml ps --format "{{.Service}} {{.Status}}" | grep -c "healthy") -lt 5 ]; do
    sleep 5
    echo "Waiting for services..."
done

# Start Kong API Gateway
echo -e "\n5. Starting Kong API Gateway..."
docker-compose up -d kong

# Start all microservices
echo -e "\n6. Starting microservices..."

docker run -d --name cyberepi-user-service --network cyberepi-net -p 8011:8001 \
    -e DATABASE_URL=postgresql+asyncpg://cyberepi:devpassword@postgres:5432/cyberepi \
    -e REDIS_URL=redis://redis:6379/0 \
    -e KEYCLOAK_URL=http://keycloak:8080 \
    -e JWT_SECRET_KEY=dev-secret-key \
    cyberepi/user-service:latest

docker run -d --name cyberepi-symptom-service --network cyberepi-net -p 8012:8002 \
    -e DATABASE_URL=postgresql+asyncpg://cyberepi:devpassword@postgres:5432/cyberepi \
    -e REDIS_URL=redis://redis:6379/0 \
    -e KAFKA_BOOTSTRAP_SERVERS=kafka:9092 \
    cyberepi/symptom-service:latest

docker run -d --name cyberepi-prescription-service --network cyberepi-net -p 8013:8003 \
    -e DATABASE_URL=postgresql+asyncpg://cyberepi:devpassword@postgres:5432/cyberepi \
    -e REDIS_URL=redis://redis:6379/0 \
    cyberepi/prescription-service:latest

docker run -d --name cyberepi-notification-service --network cyberepi-net -p 8014:8004 \
    -e DATABASE_URL=postgresql+asyncpg://cyberepi:devpassword@postgres:5432/cyberepi \
    -e REDIS_URL=redis://redis:6379/0 \
    -e KAFKA_BOOTSTRAP_SERVERS=kafka:9092 \
    cyberepi/notification-service:latest

docker run -d --name cyberepi-epi-engine --network cyberepi-net -p 8015:8005 \
    -e DATABASE_URL=postgresql+asyncpg://cyberepi:devpassword@postgres:5432/cyberepi \
    -e REDIS_URL=redis://redis:6379/0 \
    -e KAFKA_BOOTSTRAP_SERVERS=kafka:9092 \
    cyberepi/epi-engine:latest

docker run -d --name cyberepi-privacy-service --network cyberepi-net -p 8016:8006 \
    -e DATABASE_URL=postgresql+asyncpg://cyberepi:devpassword@postgres:5432/cyberepi \
    -e REDIS_URL=redis://redis:6379/0 \
    cyberepi/privacy-service:latest

# Check status
echo -e "\n7. Checking service status..."
sleep 10
docker ps --filter "name=cyberepi-*" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo -e "\n=== Backend services startup complete! ==="
echo -e "\nAPI Gateway: http://localhost:8000"
echo "Keycloak Admin: http://localhost:8080 (admin/admin)"
echo -e "\nTo view logs: docker logs -f cyberepi-[service-name]"

cd ..
