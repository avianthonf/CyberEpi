
import importlib
modules = ["pytest", "pytest_asyncio", "httpx", "testcontainers", "sqlalchemy", "redis", "fastapi"]
for mod in modules:
    try:
        importlib.import_module(mod)
        print(f"{mod}: OK")
    except ImportError as e:
        print(f"{mod}: MISSING ({e})")
