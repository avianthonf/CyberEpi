# Security Cleanup Report

## Summary of Changes

- **`libs/shared/src/shared/auth.py`**: Removed `DEBUG` bypass in JWT authentication. Production now always enforces JWT validation.
- **`services/epi-engine/src/api/routers/control.py`**: Replaced auth mock with `get_current_user` dependency in `update_control_weights`.
- **`services/epi-engine/src/main.py`**: Removed Kafka producer mock and enabled real connection.
- **`services/epi-engine/src/tasks/control_tasks.py`**: Replaced Kafka producer mock with `AIOKafkaProducer` implementation.
- **`scripts/services-up.sh`**: Changed `DEBUG` export from `True` to `False`.

## Verified
- All identified testing bypasses in production services have been removed.
- Tests (mocks in `tests/` directories) remain intact.