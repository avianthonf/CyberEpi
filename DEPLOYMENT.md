# CyberEpi Free Deployment Guide

This guide provides step-by-step instructions to deploy CyberEpi on various free cloud platforms.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Platform Options](#platform-options)
3. [Render Deployment](#render-deployment)
4. [Railway Deployment](#railway-deployment)
5. [Fly.io Deployment](#flyio-deployment)
6. [Vercel Deployment](#vercel-deployment)
7. [Kubernetes (Free Tier)](#kubernetes-free-tier)
8. [Environment Variables](#environment-variables)
9. [Monitoring & Maintenance](#monitoring--maintenance)

## Prerequisites

- Docker installed locally
- Git repository with your CyberEpi code
- Accounts on chosen cloud platforms
- Domain name (optional, for custom URLs)

## Platform Options

| Platform | Free Tier Limits | Best For | Complexity |
|----------|------------------|----------|------------|
| Render | 750 hours/month, 1GB RAM | Beginners | Low |
| Railway | $5 credit/month, 500hrs | Developers | Low |
| Fly.io | 160-240 hours shared CPU | Global deployment | Medium |
| Vercel | Serverless functions | API endpoints | Medium |
| GKE/AKS (Free) | 1 node cluster | Production | High |

## Render Deployment

### Step 1: Prepare Your Repository
```bash
# Create a render.yaml configuration in your root
cp deploy/free/render.yaml render.yaml
```

### Step 2: Set Up Environment Variables
In Render Dashboard:
1. Go to Environment Variables
2. Add these variables:
   - `POSTGRES_PASSWORD`: Generate a strong password
   - `DATABASE_URL`: `postgresql://cyberepi:${POSTGRES_PASSWORD}@postgres:5432/cyberepi`

### Step 3: Deploy Services
1. Connect your GitHub repository to Render
2. Render will automatically detect services from `render.yaml`
3. Deploy in this order:
   - postgres (Database)
   - redis (Cache)
   - All microservices

### Step 4: Configure API Gateway
```bash
# Update Kong configuration to use Render URLs
# Edit infra/kong/kong.yml with your service URLs
```

## Railway Deployment

### Step 1: Install Railway CLI
```bash
npm install -g @railway/cli
```

### Step 2: Login and Initialize
```bash
railway login
railway init
```

### Step 3: Configure Services
```bash
# Copy railway configuration
cp deploy/free/railway.toml railway.toml

# Add PostgreSQL
railway add postgresql

# Add Redis
railway add redis
```

### Step 4: Deploy Each Service
```bash
# Deploy from each service directory
cd services/user-service
railway up

cd ../symptom-service
railway up

# ... repeat for all services
```

### Step 5: Set Environment Variables
```bash
railway variables set DATABASE_URL=$DATABASE_URL
railway variables set REDIS_URL=$REDIS_URL
```

## Fly.io Deployment

### Step 1: Install Fly CLI
```bash
curl -L https://fly.io/install.sh | sh
```

### Step 2: Authentication
```bash
fly auth signup
fly auth login
```

### Step 3: Launch Apps
```bash
# Deploy each service as a separate app
fly launch --name cyberepi-epi-engine --region sjc
fly deploy

# For database
fly postgres create --name cyberepi-db
fly postgres attach --app cyberepi-epi-engine cyberepi-db

# For Redis
fly redis create --name cyberepi-redis
```

### Step 4: Configure Networking
```bash
# Create private network for services
fly ips allocate-v6
fly ips allocate-v4
```

## Vercel Deployment

### Step 1: Install Vercel CLI
```bash
npm install -g vercel
```

### Step 2: Configure Serverless Functions
```bash
# Create vercel.json in root
cp deploy/free/vercel.json vercel.json
```

### Step 3: Deploy Each Service
```bash
# Deploy from service directories
cd services/user-service
vercel --prod

cd ../symptom-service
vercel --prod
```

### Step 4: Set Up External Services
- Use PlanetScale for PostgreSQL (free tier)
- Use Upstash for Redis (free tier)
- Use Confluent Cloud for Kafka (free tier)

## Kubernetes (Free Tier)

### Option 1: Google Kubernetes Engine (GKE)
```bash
# Create GKE cluster (free tier: 1 e2-micro node)
gcloud container clusters create cyberepi \
  --num-nodes=1 \
  --machine-type=e2-micro \
  --region=us-central1

# Get credentials
gcloud container clusters get-credentials cyberepi
```

### Option 2: Azure Kubernetes Service (AKS)
```bash
# Create AKS cluster (free tier: 1 node)
az aks create \
  --resource-group cyberepi-rg \
  --name cyberepi \
  --node-count 1 \
  --node-vm-size Standard_B2s \
  --generate-ssh-keys
```

### Step 2: Deploy Infrastructure
```bash
# Apply namespaces
kubectl apply -f infra/k8s/namespaces.yaml

# Deploy storage and databases
kubectl apply -f infra/k8s/postgres/
kubectl apply -f infra/k8s/redis/
kubectl apply -f infra/k8s/kafka/
```

### Step 3: Deploy Services
```bash
# Deploy all services
kubectl apply -f infra/k8s/services/
```

### Step 4: Configure API Gateway
```bash
# Deploy Kong gateway and route rules
kubectl apply -f infra/k8s/kong/
```

## Environment Variables

Create a `.env.production` file:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://cyberepi:PASSWORD@HOST:5432/cyberepi

# Redis
REDIS_URL=redis://HOST:6379/0

# Kafka
KAFKA_BOOTSTRAP_SERVERS=HOST:9092

# Keycloak
KEYCLOAK_URL=https://your-keycloak-url.com
KEYCLOAK_REALM=cyberepi

# Service Ports
SERVICE_PORT_USER=8001
SERVICE_PORT_SYMPTOM=8002
SERVICE_PORT_PRESCRIPTION=8003
SERVICE_PORT_NOTIFICATION=8004
SERVICE_PORT_EPI=8005
SERVICE_PORT_PRIVACY=8006

# Security
JWT_SECRET_KEY=your-jwt-secret
ENCRYPTION_KEY=your-encryption-key

# External APIs
OPENFDA_API_URL=https://api.fda.gov
RXNORM_API_URL=https://rxnav.nlm.nih.gov/REST
```

## Monitoring & Maintenance

### 1. Health Checks
All services include health check endpoints:
- `/health` - Basic health status
- `/ready` - Readiness probe
- `/metrics` - Prometheus metrics

### 2. Logging
- Use structured logging with structlog
- Configure log aggregation (Loki/ELK stack)
- Set up alerts for critical errors

### 3. Backup Strategy
```bash
# PostgreSQL backup
pg_dump cyberepi > backup_$(date +%Y%m%d).sql

# Redis backup
redis-cli BGSAVE
```

### 4. Scaling
- Horizontal scaling: Increase replicas
- Vertical scaling: Upgrade instance sizes
- Database: Read replicas for read-heavy workloads

## Cost Optimization Tips

1. **Use smallest viable instances**
2. **Enable auto-shutdown for dev environments**
3. **Use spot instances where possible**
4. **Compress and cache static assets**
5. **Monitor resource usage regularly**
6. **Clean up unused resources**

## Troubleshooting

### Common Issues

1. **Database Connection Errors**
   - Check DATABASE_URL format
   - Verify network connectivity
   - Check firewall rules

2. **Service Discovery Issues**
   - Verify service names match
   - Check DNS resolution
   - Review network policies

3. **Memory Issues**
   - Monitor memory usage
   - Add memory limits
   - Optimize Python code

4. **Slow Performance**
   - Check database queries
   - Add Redis caching
   - Enable connection pooling

### Debug Commands
```bash
# Check pod status
kubectl get pods -n cyberepi-dev

# View logs
kubectl logs -f deployment/epi-engine -n cyberepi-dev

# Port forward for local testing
kubectl port-forward svc/epi-engine 8005:8005 -n cyberepi-dev
```

## Security Checklist

- [ ] Change default passwords
- [ ] Enable HTTPS everywhere
- [ ] Set up CORS properly
- [ ] Use environment variables for secrets
- [ ] Enable audit logging
- [ ] Set up rate limiting
- [ ] Monitor for vulnerabilities
- [ ] Regular security updates

## Next Steps

1. Set up CI/CD pipeline
2. Configure automated backups
3. Set up monitoring dashboards
4. Plan disaster recovery
5. Document architecture decisions

## Support

For deployment issues:
1. Check platform documentation
2. Review service logs
3. Test with minimal configuration
4. Join community forums
5. Create GitHub issues with details

Remember: Free tiers have limitations. Monitor usage to avoid unexpected charges.
