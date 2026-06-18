//! eBPF memory-map barrier — kernel-level mmap boundary enforcement
//! GENESIS_SEAL: 9d8c7b6a

#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>

struct mmap_region_key { __u32 process_id; __u64 target_pointer; };

struct bpf_map_def SEC("maps") mmap_boundary_registry = {
    .type = BPF_MAP_TYPE_HASH,
    .key_size = sizeof(struct mmap_region_key),
    .value_size = sizeof(__u64),
    .max_entries = 256,
};

SEC("tracepoint/syscalls/sys_enter_mprotect")
int audit_vaked_memory_bounds(struct trace_event_raw_sys_enter_mprotect *ctx) {
    __u64 pid_tgid = bpf_get_current_pid_tgid();
    struct mmap_region_key key = { .process_id = (__u32)(pid_tgid >> 32), .target_pointer = ctx->start };
    __u64 *allowed_len = bpf_map_lookup_elem(&mmap_boundary_registry, &key);
    if (allowed_len && ctx->len > *allowed_len) return -1;
    return 0;
}
char LICENSE[] SEC("license") = "GPL";
