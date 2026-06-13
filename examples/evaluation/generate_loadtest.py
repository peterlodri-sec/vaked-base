#!/usr/bin/env python3
"""Generate load test .vaked files with N parallel workers for scalability benchmarking.

Usage:
  python3 generate_loadtest.py --workers 64 --out swe-swarm-64-workers.vaked
  python3 generate_loadtest.py --workers 1024 --out swe-swarm-1k-workers.vaked
  python3 generate_loadtest.py --workers 10000 --out swe-swarm-10k-workers.vaked
"""

import argparse
from pathlib import Path


def generate_loadtest(num_workers: int, output_path: Path) -> None:
    """Generate a Vaked load test file with num_workers parallel fibers."""

    lines = [
        'use "./engines/zig.vaked"',
        '',
        f'# Scalability load test: {num_workers} parallel workers',
        '# Tests compiler performance on large fan-out and convergence topologies',
        '',
        f'runtime "swe-swarm-{num_workers}" {{',
        '  systems = ["x86_64-linux"]',
        '',
        '  fiber coordinator {',
        '    engine = zigDaemon',
        '    input = stream.workQueue',
        '    output = artifacts.coordinatorResults',
        '    policy { role = "coordinator" }',
        '  }',
        '',
        f'  # Worker pool ({num_workers} parallel workers)',
    ]

    # Generate worker fibers
    for i in range(1, num_workers + 1):
        worker_name = f"worker_{i:06d}"  # Zero-padded for consistency
        lines.append(f'  fiber {worker_name} {{')
        lines.append('    engine = zigDaemon')
        lines.append('    input = artifacts.codeSnapshot')
        lines.append('    output = artifacts.workerResults')
        lines.append('    policy { role = "worker" }')
        lines.append('  }')

    lines.extend([
        '',
        '  fiber aggregator {',
        '    engine = zigDaemon',
        '    input = artifacts.workerResults',
        '    output = artifacts.aggregatedResults',
        '    policy { role = "aggregator" }',
        '  }',
        '',
        '  index codebase {',
        '    source = github("example/codebase")',
        '    emit = [nix.derivation]',
        '  }',
        '',
        '  stream workQueue {',
        '    source = agentGuardd.events',
        '    type = Event.WorkItem',
        '    retention = 1h',
        '  }',
        '',
        '  # Fan-out: coordinator to all workers',
    ])

    # Generate coordinator->worker meshes
    for i in range(1, num_workers + 1):
        worker_name = f"worker_{i:06d}"
        lines.append(f'  mesh coordinator -> {worker_name}')

    lines.append('')
    lines.append('  # Convergence: all workers to aggregator')

    # Generate worker->aggregator meshes
    for i in range(1, num_workers + 1):
        worker_name = f"worker_{i:06d}"
        lines.append(f'  mesh {worker_name} -> aggregator')

    # Generate worker list for parallel declaration (all workers)
    worker_list_items = [f'worker_{i:06d}' for i in range(1, num_workers + 1)]

    lines.extend([
        '',
        f'  parallel "worker-pool-{num_workers}" {{',
    ])

    # Format as a list, line-wrapped for readability
    lines.append('    fibers = [')
    for i, worker in enumerate(worker_list_items):
        if (i + 1) % 10 == 0:
            lines.append(f'      {worker},')
        elif i == len(worker_list_items) - 1:
            lines.append(f'      {worker}')
        else:
            lines.append(f'      {worker},')
    lines.append('    ]')
    lines.extend([
        '    strategy = "concurrent"',
        '    supervisor = otp',
        '  }',
        '}',
    ])

    content = '\n'.join(lines)
    output_path.write_text(content)
    print(f"Generated {output_path} with {num_workers} workers ({len(content)} bytes)")


def main():
    parser = argparse.ArgumentParser(description='Generate Vaked load test files')
    parser.add_argument('--workers', type=int, required=True, help='Number of workers')
    parser.add_argument('--out', type=Path, required=True, help='Output file path')
    args = parser.parse_args()

    generate_loadtest(args.workers, args.out)


if __name__ == '__main__':
    main()
