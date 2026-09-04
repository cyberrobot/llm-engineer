def test_production_modules_do_not_depend_on_backend_implementation():
    from pathlib import Path

    service_root = Path(__file__).parents[1]
    for source in service_root.glob("*.py"):
        content = source.read_text(encoding="utf-8")
        assert "apps/backend" not in content
        assert "sys.path" not in content
        assert "from assistant" not in content
        assert "from core" not in content
        assert "from shared" not in content
