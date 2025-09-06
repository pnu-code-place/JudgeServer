import hashlib
import logging
import os
import socket

import _judger
import psutil
from config import SERVER_LOG_PATH
from exception import JudgeClientError

logger = logging.getLogger(__name__)
handler = logging.FileHandler(SERVER_LOG_PATH)
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.WARNING)


def get_available_cpu_count():
    """
    Get the actual available CPU count considering cgroup limits (Docker/Kubernetes).
    Falls back to psutil.cpu_count() if cgroup info is not available.
    """
    try:
        # Try cgroup v2 first
        cpu_max_path = "/sys/fs/cgroup/cpu.max"
        if os.path.exists(cpu_max_path):
            with open(cpu_max_path, "r") as f:
                cpu_max = f.read().strip()
                if cpu_max != "max":
                    # Format: "quota period" (e.g., "100000 100000" means 1 CPU)
                    parts = cpu_max.split()
                    if len(parts) == 2:
                        quota = int(parts[0])
                        period = int(parts[1])
                        if quota > 0 and period > 0:
                            cpu_count = max(1, int(quota / period))
                            logger.info(f"Using cgroup v2 CPU count: {cpu_count}")
                            return cpu_count

        # Try cgroup v1
        cpu_quota_path = "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"
        cpu_period_path = "/sys/fs/cgroup/cpu/cpu.cfs_period_us"

        if os.path.exists(cpu_quota_path) and os.path.exists(cpu_period_path):
            with open(cpu_quota_path, "r") as f:
                quota = int(f.read().strip())
            with open(cpu_period_path, "r") as f:
                period = int(f.read().strip())

            if quota > 0 and period > 0:
                cpu_count = max(1, int(quota / period))
                logger.info(f"Using cgroup v1 CPU count: {cpu_count}")
                return cpu_count

        # Try cpuset (cgroup v1/v2)
        cpuset_paths = [
            "/sys/fs/cgroup/cpuset.cpus.effective",  # cgroup v2
            "/sys/fs/cgroup/cpuset/cpuset.cpus",  # cgroup v1
        ]

        for cpuset_path in cpuset_paths:
            if os.path.exists(cpuset_path):
                with open(cpuset_path, "r") as f:
                    cpus = f.read().strip()
                    if cpus:
                        # Parse CPU list (e.g., "0-3", "0,2-4", "1")
                        cpu_count = len(_parse_cpu_list(cpus))
                        if cpu_count > 0:
                            logger.info(f"Using cpuset CPU count: {cpu_count}")
                            return cpu_count

    except Exception as e:
        logger.warning(f"Failed to read cgroup CPU info: {e}")

    # Fallback to psutil
    cpu_count = psutil.cpu_count()
    logger.info(f"Using psutil CPU count (fallback): {cpu_count}")
    return cpu_count


def _parse_cpu_list(cpu_list_str):
    """
    Parse CPU list string like "0-3", "0,2-4", "1" into a set of CPU indices.
    """
    cpus = set()
    for part in cpu_list_str.split(","):
        if "-" in part:
            start, end = map(int, part.split("-"))
            cpus.update(range(start, end + 1))
        else:
            cpus.add(int(part))
    return cpus


def server_info():
    ver = _judger.VERSION
    return {
        "hostname": socket.gethostname(),
        "cpu": psutil.cpu_percent(),
        "cpu_core": get_available_cpu_count(),
        "memory": psutil.virtual_memory().percent,
        "judger_version": ".".join(
            [str((ver >> 16) & 0xFF), str((ver >> 8) & 0xFF), str(ver & 0xFF)]
        ),
    }


def get_token():
    token = os.environ.get("TOKEN")
    if token:
        return token
    else:
        raise JudgeClientError("env 'TOKEN' not found")


class ProblemIOMode:
    standard = "Standard IO"
    file = "File IO"


token = hashlib.sha256(get_token().encode("utf-8")).hexdigest()
