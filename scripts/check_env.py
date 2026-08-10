import importlib

for mod in ["requests", "dotenv", "pydantic", "pytest"]:
    try:
        m = importlib.import_module(mod)
        print(mod, "OK", getattr(m, "__version__", ""))
    except Exception as exc:
        print(mod, "MISSING", exc)
