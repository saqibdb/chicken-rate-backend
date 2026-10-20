from .models import EnvironmentVariable


def get_runtime_setting(name, fallback=""):
    """Return an admin-configured value, falling back to the process environment."""
    record = EnvironmentVariable.objects.filter(name=name).only("value").first()
    return record.value if record is not None else fallback
