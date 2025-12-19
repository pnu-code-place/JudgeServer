#!/bin/sh
set -ex

rm -rf /judger/*
mkdir -p /judger/run /judger/spj

chown compiler:code /judger/run
chmod 711 /judger/run

chown compiler:spj /judger/spj
chmod 710 /judger/spj

DEFAULT_WORKER_NUM=4

# 워커 수가 지정되지 않은 경우 cgroup 제한에 따라 자동으로 설정
if [ -z "$WORKER_NUM" ]; then
    # cgroup v2
    if [ -f "/sys/fs/cgroup/cpu.max" ]; then
        CPU_MAX=$(cat /sys/fs/cgroup/cpu.max)
        if [ "$CPU_MAX" != "max" ]; then
            CPU_QUOTA=$(echo "$CPU_MAX" | cut -d' ' -f1)
            CPU_PERIOD=$(echo "$CPU_MAX" | cut -d' ' -f2)

            if [ -n "$CPU_QUOTA" ] && [ -n "$CPU_PERIOD" ] && [ "$CPU_PERIOD" -gt 0 ]; then
                export WORKER_NUM=$((CPU_QUOTA / CPU_PERIOD))
            fi
        fi
    # cgroup v1
    elif [ -f "/sys/fs/cgroup/cpu/cpu.cfs_quota_us" ] && [ -f "/sys/fs/cgroup/cpu/cpu.cfs_period_us" ]; then
        CPU_QUOTA=$(cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us)
        CPU_PERIOD=$(cat /sys/fs/cgroup/cpu/cpu.cfs_period_us)

        if [ "$CPU_QUOTA" -gt 0 ] && [ "$CPU_PERIOD" -gt 0 ]; then
            export WORKER_NUM=$((CPU_QUOTA / CPU_PERIOD))
        fi
    fi

    # cgroup에서 워커 수를 가져오지 못한 경우 기본값을 사용
    if [ -z "$WORKER_NUM" ] || [ "$WORKER_NUM" -eq 0 ]; then
        export WORKER_NUM=${DEFAULT_WORKER_NUM}
    fi
fi

exec .venv/bin/gunicorn server:app --workers $WORKER_NUM --threads 4 --error-logfile /log/gunicorn.log --bind 0.0.0.0:8080
