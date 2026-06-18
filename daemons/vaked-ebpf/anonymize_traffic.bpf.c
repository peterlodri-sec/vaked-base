#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>
SEC("cgroup/skb")
int enforce_anonymity_ingress(struct __sk_buff *skb) {
    __u32 src_ip = skb->remote_ip4;
    if (src_ip != 0x7F000001) { skb->cb[0] = 0xEEEE; }
    return 1;
}
char LICENSE[] SEC("license") = "GPL";
