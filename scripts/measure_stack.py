#!/usr/bin/env python3
"""Read-only, project-scoped Podman measurements; never print container environments."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path


def execute_command(arguments: list[str], executed_commands: list[list[str]]) -> str:
    """Record the actual, non-secret command and require a successful result."""
    executed_commands.append(arguments)
    result = subprocess.run(arguments, capture_output=True, text=True, check=True)
    return result.stdout


def parse_memory_bytes(memory_usage: str) -> int:
    """Convert the used portion of Podman's rounded SI/IEC memory display."""
    used_memory = memory_usage.split("/", 1)[0].strip()
    match = re.fullmatch(r"([0-9.]+)\s*([A-Za-z]+)", used_memory)
    multipliers = {
        "B": 1,
        "kB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "TB": 1000**4,
        "KiB": 1024,
        "MiB": 1024**2,
        "GiB": 1024**3,
        "TiB": 1024**4,
    }
    if match is None or match.group(2) not in multipliers:
        raise ValueError(f"Unrecognized Podman memory display: {memory_usage!r}")
    return int(float(match.group(1)) * multipliers[match.group(2)])


def measure_project(project: str, samples: int, interval: float) -> dict:
    commands: list[list[str]] = []
    containers = json.loads(
        execute_command(
            [
                "podman",
                "ps",
                "-a",
                "--filter",
                f"label=io.podman.compose.project={project}",
                "--format",
                "json",
            ],
            commands,
        )
    )
    if not containers:
        raise ValueError(f"No Podman Compose containers found for project {project!r}")

    container_ids = [container["Id"] for container in containers]
    inspections = json.loads(
        execute_command(
            [
                "podman",
                "inspect",
                "--size",
                *container_ids,
            ],
            commands,
        )
    )
    running_ids = [container["Id"] for container in inspections if container["State"]["Running"]]
    image_ids = sorted({container["Image"] for container in inspections})
    images = json.loads(execute_command(["podman", "image", "inspect", *image_ids], commands))
    info = json.loads(execute_command(["podman", "info", "--format", "json"], commands))
    if info["store"]["graphDriverName"] != "overlay":
        raise ValueError("Layer measurement currently requires Podman's overlay storage driver")

    metadata_path = Path(info["store"]["graphRoot"]) / "overlay-layers" / "layers.json"
    metadata = json.loads(metadata_path.read_text())
    layers_by_digest = {layer["diff-digest"]: layer for layer in metadata if layer.get("diff-digest")}
    unique_digests = {digest for image in images for digest in image["RootFS"]["Layers"]}
    layer_sizes = {}
    for digest in sorted(unique_digests):
        if digest not in layers_by_digest or "diff-size" not in layers_by_digest[digest]:
            raise ValueError(f"Missing uncompressed size metadata for runtime layer {digest}")
        layer_sizes[digest] = layers_by_digest[digest]["diff-size"]

    # ps JSON has mountpoint strings; only inspect JSON has typed mount records.
    volume_names = sorted(
        {mount["Name"] for container in inspections for mount in container["Mounts"] if mount["Type"] == "volume"}
    )
    volume_sizes = {}
    if volume_names:
        volumes = json.loads(
            execute_command(
                [
                    "podman",
                    "volume",
                    "inspect",
                    *volume_names,
                ],
                commands,
            )
        )
        for volume in volumes:
            allocated = execute_command(
                [
                    "podman",
                    "unshare",
                    "du",
                    "-s",
                    "-B1",
                    volume["Mountpoint"],
                ],
                commands,
            )
            volume_sizes[volume["Name"]] = int(allocated.split()[0])

    memory_samples = []
    if running_ids:
        for sample_index in range(samples):
            if sample_index > 0:
                time.sleep(interval)
            statistics = json.loads(
                execute_command(
                    [
                        "podman",
                        "stats",
                        "--no-stream",
                        "--format",
                        "json",
                        *running_ids,
                    ],
                    commands,
                )
            )
            if len(statistics) != len(running_ids):
                raise ValueError("Incomplete memory sample: a project container may have stopped")
            memory_by_container = {row["name"]: parse_memory_bytes(row["mem_usage"]) for row in statistics}
            memory_samples.append(
                {
                    "timestamp": time.time(),
                    "containers": memory_by_container,
                    "total_bytes": sum(memory_by_container.values()),
                }
            )

    total_memory_bytes = None
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemTotal:"):
            total_memory_bytes = int(line.split()[1]) * 1024
            break
    if total_memory_bytes is None:
        raise ValueError("MemTotal is missing from /proc/meminfo")

    return {
        "project": project,
        "machine": {
            "uname": platform.uname()._asdict(),
            "total_memory_bytes": total_memory_bytes,
            "logical_cpus": os.cpu_count(),
            "podman": execute_command(["podman", "--version"], commands).strip(),
            "compose": execute_command(["podman-compose", "--version"], commands).strip(),
        },
        "measurements": {
            "container_count": len(inspections),
            "running_count": len(running_ids),
            "states": dict(Counter(container["State"]["Status"] for container in inspections)),
            "image_count": len(images),
            "image_ids": image_ids,
            "unique_layers": len(unique_digests),
            "deduplicated_uncompressed_layer_bytes": sum(layer_sizes.values()),
            "logical_image_bytes": sum(image["Size"] for image in images),
            "container_writable_bytes": sum(container["SizeRw"] for container in inspections),
            "volume_allocated_bytes": sum(volume_sizes.values()),
            "volume_sizes": volume_sizes,
            "memory_samples": memory_samples,
        },
        "commands": commands,
        "layer_metadata_file": str(metadata_path),
        "notes": [
            "Image layers are deduplicated uncompressed diff sizes, not physical filesystem usage.",
            "Logical image sizes count shared layers repeatedly; do not add them as disk requirements.",
            "Volume allocation and writable layers vary with project data and logs.",
            "Memory values come from rounded Podman displays, not a peak/load benchmark.",
            "Run before workload on fresh disposable volumes to describe initial idle capacity.",
            "No environment values, credentials, data records or secret-bearing commands are emitted.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Existing Podman Compose project name")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds between samples")
    arguments = parser.parse_args()
    if arguments.samples < 1 or not math.isfinite(arguments.interval) or arguments.interval <= 0:
        parser.error("--samples must be positive and --interval must be positive and finite")
    try:
        measurement = measure_project(arguments.project, arguments.samples, arguments.interval)
    except subprocess.CalledProcessError as error:
        print(f"Measurement command failed: {error.cmd!r}: {error.stderr.strip()}", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Measurement unavailable: {error}", file=sys.stderr)
        return 1
    print(json.dumps(measurement, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
