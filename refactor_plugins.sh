#!/bin/bash
rm -rf internal/plugins/skillsimprover
rm -f internal/plugins/agentfield_builtin.go internal/plugins/langfuse_plugin.go internal/plugins/nats_plugin.go internal/plugins/repomap_plugin.go internal/plugins/superpowers_plugin.go
echo "Deleted 6 files"
ls internal/plugins/*.go | wc -l
go build ./internal/plugins/ 2>&1 | head -5
echo "Build: $?"