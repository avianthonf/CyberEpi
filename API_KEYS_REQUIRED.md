# CyberEpi - Required API Keys & Configuration

This document lists all API keys, credentials, and configuration needed for full production deployment.

## 🔑 Authentication & Identity

### Keycloak (Self-hosted or Cloud)
```yaml
KEYCLOAK_URL: "https://your-keycloak-domain.com/auth"
KEYCLOAK_REALM: "cyberepi"
KEYCLOAK_CLIENT_ID: "cyberepi-backend"
KEYCLOAK_CLIENT_SECRET: "your-keycloak-client-secret"
JWT_SECRET_KEY: "your-jwt-signing-secret-256-bit-minimum"
JWKS_URL: "https://your-keycloak-domain.com/auth/realms/cyberepi/protocol/openid-connect/certs"
```

### Alternative Auth Providers (Optional)
```yaml
# Auth0
AUTH0_DOMAIN: "your-domain.auth0.com"
AUTH0_CLIENT_ID: "your-auth0-client-id"
AUTH0_CLIENT_SECRET: "your-auth0-client-secret"

# Supabase Auth
SUPABASE_URL: "https://your-project.supabase.co"
SUPABASE_ANON_KEY: "your-supabase-anon-key"
SUPABASE_SERVICE_KEY: "your-supabase-service-key"

# Firebase Auth
FIREBASE_PROJECT_ID: "your-firebase-project"
FIREBASE_PRIVATE_KEY: "-----BEGIN PRIVATE KEY-----\n..."
FIREBASE_CLIENT_EMAIL: "firebase-adminsdk-xxx@your-project.iam.gserviceaccount.com"
```

## 🏥 Healthcare APIs

### OpenFDA (Free)
```yaml
OPENFDA_API_URL: "https://api.fda.gov"
OPENFDA_API_KEY: "your-openfda-api-key"  # Optional, increases rate limits
```

### RxNorm (Free)
```yaml
RXNORM_API_URL: "https://rxnav.nlm.nih.gov/REST"
# No API key required, but rate limited
```

### Alternative Medical APIs
```yaml
# FHIR Server (Epic, Cerner, etc.)
FHIR_BASE_URL: "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/DSTU2"
FHIR_CLIENT_ID: "your-fhir-client-id"
FHIR_CLIENT_SECRET: "your-fhir-client-secret"

# IBM Micromedex
MICROMEDEX_API_KEY: "your-micromedex-key"
MICROMEDEX_URL: "https://api.micromedexsolutions.com"

# MedlinePlus
MEDLINEPLUS_API_KEY: "your-medlineplus-key"
```

## 📊 Data & Analytics APIs

### CDC Data (Free)
```yaml
CDC_API_URL: "https://data.cdc.gov/resource/"
CDC_APP_TOKEN: "your-cdc-app-token"
```

### WHO Data (Free)
```yaml
WHO_API_URL: "https://covid19.who.com/api"
WHO_API_KEY: "your-who-api-key"
```

### Johns Hopkins CSSE (Free)
```yaml
JHUCSSE_API_URL: "https://disease.sh"
# No API key required
```

## 📧 Notification Services

### SendGrid
```yaml
SENDGRID_API_KEY: "SG.your-sendgrid-api-key"
SENDGRID_FROM_EMAIL: "noreply@cyberepi.com"
SENDGRID_TEMPLATE_ALERT: "d-your-alert-template-id"
SENDGRID_TEMPLATE_REPORT: "d-your-report-template-id"
```

### Twilio (SMS)
```yaml
TWILIO_ACCOUNT_SID: "ACyourtwilioaccountsid"
TWILIO_AUTH_TOKEN: "your-twilio-auth-token"
TWILIO_PHONE_NUMBER: "+1234567890"
```

### Push Notifications
```yaml
# Firebase Cloud Messaging
FCM_SERVER_KEY: "your-fcm-server-key"
FCM_SENDER_ID: "your-fcm-sender-id"

# Apple Push Notification Service
APNS_KEY_ID: "your-apns-key-id"
APNS_TEAM_ID: "your-apple-team-id"
APNS_PRIVATE_KEY: "-----BEGIN PRIVATE KEY-----\n..."

# OneSignal
ONESIGNAL_APP_ID: "your-onesignal-app-id"
ONESIGNAL_REST_API_KEY: "your-onesignal-rest-key"
```

## ☁️ Cloud Infrastructure

### AWS (if using AWS services)
```yaml
AWS_ACCESS_KEY_ID: "AKIAIOSFODNN7EXAMPLE"
AWS_SECRET_ACCESS_KEY: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
AWS_DEFAULT_REGION: "us-east-1"

# S3
S3_BUCKET_NAME: "cyberepi-data-storage"
S3_ACCESS_KEY: "your-s3-access-key"
S3_SECRET_KEY: "your-s3-secret-key"

# SES (Email)
SES_REGION: "us-east-1"
SES_ACCESS_KEY: "your-ses-access-key"
SES_SECRET_KEY: "your-ses-secret-key"

# RDS (if not using TimescaleDB)
RDS_HOSTNAME: "cyberepi-db.cluster-xxx.us-east-1.rds.amazonaws.com"
RDS_USERNAME: "cyberepi"
RDS_PASSWORD: "your-rds-password"
RDS_DB_NAME: "cyberepi"
```

### Google Cloud
```yaml
GOOGLE_APPLICATION_CREDENTIALS: "/path/to/service-account.json"
GCP_PROJECT_ID: "your-gcp-project"

# Cloud Storage
GCS_BUCKET_NAME: "cyberepi-storage"

# BigQuery (if using for analytics)
BIGQUERY_DATASET: "cyberepi_analytics"
```

### Azure
```yaml
AZURE_CLIENT_ID: "your-azure-client-id"
AZURE_CLIENT_SECRET: "your-azure-client-secret"
AZURE_TENANT_ID: "your-azure-tenant-id"
AZURE_SUBSCRIPTION_ID: "your-azure-subscription-id"
```

## 🗄️ Database Credentials

### PostgreSQL/TimescaleDB
```yaml
DATABASE_URL: "postgresql+asyncpg://cyberepi:your-secure-password@host:5432/cyberepi"
POSTGRES_USER: "cyberepi"
POSTGRES_PASSWORD: "your-secure-postgres-password"
POSTGRES_HOST: "localhost"  # or your db host
POSTGRES_PORT: "5432"
POSTGRES_DB: "cyberepi"
```

### Redis
```yaml
REDIS_URL: "redis://:your-redis-password@host:6379/0"
REDIS_PASSWORD: "your-redis-password"
REDIS_HOST: "localhost"
REDIS_PORT: "6379"
REDIS_DB: "0"
```

### MongoDB (Alternative)
```yaml
MONGODB_URL: "mongodb://username:password@host:27017/cyberepi"
MONGODB_USER: "cyberepi"
MONGODB_PASSWORD: "your-mongodb-password"
```

## 📨 Message Queue

### Kafka (Self-hosted)
```yaml
KAFKA_BOOTSTRAP_SERVERS: "kafka1:9092,kafka2:9092,kafka3:9092"
KAFKA_SASL_USERNAME: "your-kafka-username"
KAFKA_SASL_PASSWORD: "your-kafka-password"
KAFKA_SECURITY_PROTOCOL: "SASL_SSL"
KAFKA_SASL_MECHANISM: "SCRAM-SHA-256"
```

### Confluent Cloud
```yaml
CONFLUENT_BOOTSTRAP_SERVERS: "pkc-xxxxx.us-east-1.aws.confluent.cloud:9092"
CONFLUENT_API_KEY: "your-confluent-api-key"
CONFLUENT_API_SECRET: "your-confluent-api-secret"
```

### AWS SQS/SNS
```yaml
AWS_SQS_ACCESS_KEY: "your-sqs-access-key"
AWS_SQS_SECRET_KEY: "your-sqs-secret-key"
AWS_SQS_REGION: "us-east-1"
AWS_SQS_QUEUE_URL: "https://sqs.us-east-1.amazonaws.com/123456789/cyberepi-queue"
```

## 🌍 Geospatial & Mapping

### Google Maps API
```yaml
GOOGLE_MAPS_API_KEY: "your-google-maps-api-key"
GEOCODING_API_KEY: "your-google-geocoding-key"
```

### Mapbox
```yaml
MAPBOX_ACCESS_TOKEN: "pk.your-mapbox-access-token"
MAPBOX_API_URL: "https://api.mapbox.com"
```

### OpenStreetMap (Nominatim - Free)
```yaml
NOMINATIM_URL: "https://nominatim.openstreetmap.org"
# No API key required, but be respectful of usage limits
```

## 🔍 Search & Analytics

### Elasticsearch
```yaml
ELASTICSEARCH_URL: "https://your-cluster.es.us-east-1.aws.elastic-cloud.com:9243"
ELASTICSEARCH_USERNAME: "elastic"
ELASTICSEARCH_PASSWORD: "your-elastic-password"
```

### Algolia (Search)
```yaml
ALGOLIA_APP_ID: "your-algolia-app-id"
ALGOLIA_ADMIN_KEY: "your-algolia-admin-key"
ALGOLIA_SEARCH_KEY: "your-algolia-search-key"
```

## 🤖 Machine Learning APIs

### OpenAI (GPT for symptom analysis)
```yaml
OPENAI_API_KEY: "sk-your-openai-api-key"
OPENAI_ORG_ID: "org-your-openai-org-id"
```

### Google Cloud AI
```yaml
GOOGLE_AI_API_KEY: "your-google-ai-api-key"
```

### AWS SageMaker
```yaml
SAGEMAKER_ACCESS_KEY: "your-sagemaker-access-key"
SAGEMAKER_SECRET_KEY: "your-sagemaker-secret-key"
SAGEMAKER_ENDPOINT_NAME: "cyberepi-prediction-endpoint"
```

## 📈 Monitoring & Observability

### DataDog
```yaml
DATADOG_API_KEY: "your-datadog-api-key"
DATADOG_APP_KEY: "your-datadog-app-key"
DATADOG_SITE: "datadoghq.com"
```

### New Relic
```yaml
NEW_RELIC_LICENSE_KEY: "your-newrelic-license-key"
NEW_RELIC_APP_NAME: "CyberEpi"
```

### Sentry (Error Tracking)
```yaml
SENTRY_DSN: "https://your-sentry-dsn@sentry.io/project-id"
SENTRY_AUTH_TOKEN: "your-sentry-auth-token"
```

### Prometheus (if using remote storage)
```yaml
PROMETHEUS_REMOTE_WRITE_URL: "https://prometheus-remote-write.example.com/api/v1/write"
PROMETHEUS_REMOTE_WRITE_USERNAME: "your-prometheus-username"
PROMETHEUS_REMOTE_WRITE_PASSWORD: "your-prometheus-password"
```

## 🔒 Security & Compliance

### VirusTotal (File scanning)
```yaml
VIRUSTOTAL_API_KEY: "your-virustotal-api-key"
```

### Recaptcha (Bot protection)
```yaml
RECAPTCHA_SITE_KEY: "6Leyour-recaptcha-site-key"
RECAPTCHA_SECRET_KEY: "6Leyour-recaptcha-secret-key"
```

### Akamai / Cloudflare
```yaml
CLOUDFLARE_API_TOKEN: "your-cloudflare-api-token"
CLOUDFLARE_ZONE_ID: "your-cloudflare-zone-id"
```

## 💳 Payment (if premium features)

### Stripe
```yaml
STRIPE_PUBLISHABLE_KEY: "pk_test_your-stripe-publishable-key"
STRIPE_SECRET_KEY: "sk_test_your-stripe-secret-key"
STRIPE_WEBHOOK_SECRET: "whsec_your-webhook-secret"
```

## 📱 Third-party Integrations

### Slack (Notifications)
```yaml
SLACK_BOT_TOKEN: "xoxb-your-slack-bot-token"
SLACK_WEBHOOK_URL: "https://hooks.slack.com/services/your/webhook/url"
SLACK_CHANNEL: "#cyberepi-alerts"
```

### Microsoft Teams
```yaml
TEAMS_WEBHOOK_URL: "https://outlook.office.com/webhook/your-teams-webhook"
```

### PagerDuty (Incident management)
```yaml
PAGERDUTY_INTEGRATION_KEY: "your-pagerduty-integration-key"
PAGERDUTY_API_KEY: "your-pagerduty-api-key"
```

## 🧪 Testing & Development

### Test Data Providers
```yaml
# Mock API providers for testing
MOCK_FDA_API: "true"
MOCK_SMS_PROVIDER: "true"
MOCK_EMAIL_PROVIDER: "true"
```

## 📝 Environment-Specific Notes

### Development Environment
```yaml
ENVIRONMENT: "development"
DEBUG: "true"
LOG_LEVEL: "DEBUG"
SSL_VERIFY: "false"
```

### Staging Environment
```yaml
ENVIRONMENT: "staging"
DEBUG: "false"
LOG_LEVEL: "INFO"
SSL_VERIFY: "true"
```

### Production Environment
```yaml
ENVIRONMENT: "production"
DEBUG: "false"
LOG_LEVEL: "WARNING"
SSL_VERIFY: "true"
SECURE_COOKIES: "true"
HSTS_ENABLED: "true"
```

## 🔐 Security Best Practices

1. **Never commit API keys to Git**
2. **Use different keys for each environment**
3. **Rotate keys regularly**
4. **Use key management services** (AWS KMS, Azure Key Vault, etc.)
5. **Implement IP whitelisting** where possible
6. **Use short-lived tokens** (JWT expiry < 1 hour)
7. **Monitor API usage** for anomalies

## 📋 API Key Management Tools

- **AWS Secrets Manager**
- **Azure Key Vault**
- **HashiCorp Vault**
- **Google Secret Manager**
- **Docker Secrets** (for Swarm)
- **Kubernetes Secrets** (for K8s)

## 🚀 Quick Setup Checklist

### Minimum for Testing (Free Tier)
- [ ] PostgreSQL password
- [ ] Redis password
- [ ] JWT secret key
- [ ] Basic email (SendGrid trial)

### Minimum for Production
- [ ] All database credentials
- [ ] Auth provider setup
- [ ] Email service (SendGrid)
- [ ] SMS service (Twilio)
- [ ] Monitoring (Sentry + DataDog)
- [ ] Backup credentials

### Full Enterprise Setup
- [ ] All of the above
- [ ] Healthcare APIs (OpenFDA, FHIR)
- [ ] Advanced monitoring
- [ ] Compliance tools
- [ ] Payment processing
- [ ] Advanced security

---

**Remember**: Start with minimum required keys and add more as needed. Always use environment variables or secret management - never hardcode credentials!
