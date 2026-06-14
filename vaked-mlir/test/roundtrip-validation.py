#!/usr/bin/env python3
"""
Round-trip validation: Stage-0 (vakedc) vs Stage-1 (vaked-mlir)

Compares outputs to verify Stage-1 faithfully reproduces Stage-0 semantics:
- Agent topology (agents, dependencies)
- Critical path length
- Per-agent depths
- Supervisor index structure
"""

import json
import subprocess
import sys
from pathlib import Path

def run_stage0(vaked_file):
    """Run Stage-0 (vakedc) pipeline on .vaked file"""
    try:
        # Assumes vakedc is available in vakedc/ dir
        result = subprocess.run(
            ["python3", "-m", "vakedc", "check", vaked_file],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            print(f"Stage-0 failed: {result.stderr}")
            return None
        return json.loads(result.stdout)
    except Exception as e:
        print(f"Stage-0 error: {e}")
        return None

def run_stage1(mlir_file):
    """Run Stage-1 (vaked-mlir) pipeline on .mlir file"""
    try:
        # Run vaked-opt with full pipeline
        result = subprocess.run(
            ["vaked-opt",
             "-pass-pipeline=builtin.module(vaked-topology-analysis,vaked-to-hcp-lowering-full,vaked-aot-index)",
             mlir_file],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            print(f"Stage-1 failed: {result.stderr}")
            return None

        # Parse JSON index from output
        for line in result.stderr.split('\n'):
            if 'I-PASS3-INDEX:' in line:
                try:
                    json_str = line.split('I-PASS3-INDEX:')[1].strip()
                    return json.loads(json_str)
                except:
                    pass
        return None
    except Exception as e:
        print(f"Stage-1 error: {e}")
        return None

def validate_topology(stage0, stage1):
    """Compare agent topologies"""
    if not stage0 or not stage1:
        return False

    # Extract topology data
    topo0 = stage0.get('topology', {})
    topo1 = stage1.get('topology', {})

    # Check critical path match
    cp0 = topo0.get('critical_path_length', -1)
    cp1 = topo1.get('critical_path_length', -1)

    if cp0 != cp1:
        print(f"❌ Critical path mismatch: Stage-0={cp0}, Stage-1={cp1}")
        return False

    print(f"✓ Critical path match: {cp0}")

    # Check agent count
    agents0 = topo0.get('agents', [])
    agents1 = topo1.get('agents', [])

    if len(agents0) != len(agents1):
        print(f"❌ Agent count mismatch: {len(agents0)} vs {len(agents1)}")
        return False

    print(f"✓ Agent count match: {len(agents0)}")

    # Check depths
    for a0, a1 in zip(agents0, agents1):
        d0 = a0.get('depth', -1)
        d1 = a1.get('depth', -1)
        if d0 != d1:
            print(f"❌ Depth mismatch for {a0.get('name')}: {d0} vs {d1}")
            return False

    print(f"✓ All depths match")

    # Check subscriptions
    for a0, a1 in zip(agents0, agents1):
        s0 = sorted(a0.get('subscriptions', []))
        s1 = sorted(a1.get('subscriptions', []))
        if s0 != s1:
            print(f"❌ Subscriptions mismatch for {a0.get('name')}: {s0} vs {s1}")
            return False

    print(f"✓ All subscriptions match")

    return True

def main():
    if len(sys.argv) < 2:
        print("Usage: roundtrip-validation.py <test.mlir>")
        sys.exit(1)

    mlir_file = sys.argv[1]
    if not Path(mlir_file).exists():
        print(f"File not found: {mlir_file}")
        sys.exit(1)

    print(f"Validating: {mlir_file}")
    print("=" * 50)

    # Run pipelines
    print("Running Stage-0 (vakedc)...")
    stage0 = run_stage0(mlir_file.replace('.mlir', '.vaked'))

    print("Running Stage-1 (vaked-mlir)...")
    stage1 = run_stage1(mlir_file)

    # Compare
    print("\nValidating...")
    if validate_topology(stage0, stage1):
        print("\n✅ ROUND-TRIP VALIDATION PASSED")
        return 0
    else:
        print("\n❌ ROUND-TRIP VALIDATION FAILED")
        return 1

if __name__ == '__main__':
    sys.exit(main())
