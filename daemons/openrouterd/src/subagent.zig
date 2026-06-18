const std=@import("std");
pub const SubagentKind=enum(u8){hydrator=0,verifier=1,synthesizer=2};
pub const ArenaMsg=extern struct{kind:SubagentKind align(64),id:u32,status:u8,payload_len:u32,payload:[4096]u8,result_len:u32,result:[8192]u8,_pad:[56]u8};
pub const ArenaHeader=extern struct{magic:u32 align(64),msg_count:u16,active_hydrators:u8,active_verifiers:u8,active_synthesizers:u8,msgs:[256]ArenaMsg};
pub const WorkerPool=struct{arena:*ArenaHeader,allocator:std.mem.Allocator,max_tool_calls:u32,
pub fn init(a:std.mem.Allocator,mmap:[]align(std.mem.page_size)u8)WorkerPool{const h=@as(*ArenaHeader,@ptrCast(@alignCast(mmap.ptr)));h.magic=0x7C242080;return WorkerPool{.arena=h,.allocator=a,.max_tool_calls=500};}
pub fn spawnHydrator(self:*WorkerPool,p:[]const u8)!u32{return self._spawn(.hydrator,p);}
pub fn spawnVerifier(self:*WorkerPool,d:[]const u8)!u32{return self._spawn(.verifier,d);}
pub fn spawnSynthesizer(self:*WorkerPool,t:[]const u8)!u32{return self._spawn(.synthesizer,t);}
fn _spawn(self:*WorkerPool,k:SubagentKind,p:[]const u8)!u32{
    var i:usize=0;while(i<256):(i+=1){
        var m=&self.arena.msgs[i];
        const old=@atomicRmw(u8,&m.status,.Xchg,1,.acquire);
        if(old==0){
            m.kind=k;m.id=@intCast(i);m.payload_len=@intCast(@min(p.len,4095));
            @memcpy(m.payload[0..m.payload_len],p[0..m.payload_len]);
            switch(k){
                .hydrator=>{_=@atomicRmw(u8,&self.arena.active_hydrators,.Add,1,.monotonic);},
                .verifier=>{_=@atomicRmw(u8,&self.arena.active_verifiers,.Add,1,.monotonic);},
                .synthesizer=>{_=@atomicRmw(u8,&self.arena.active_synthesizers,.Add,1,.monotonic);},
            }
            return @intCast(i);
        }
    }
    return error.PoolFull;
}
pub fn poll(self:*WorkerPool,id:u32)?[]const u8{
    if(id>=256)return null;const m=&self.arena.msgs[id];
    if(@atomicLoad(u8,&m.status,.acquire)==2)return m.result[0..m.result_len];
    return null;
}
pub fn complete(self:*WorkerPool,id:u32,r:[]const u8)void{
    if(id>=256)return;var m=&self.arena.msgs[id];
    m.result_len=@intCast(@min(r.len,8191));
    @memcpy(m.result[0..m.result_len],r[0..m.result_len]);
    @atomicStore(u8,&m.status,2,.release); // visible to poll() on other threads
    switch(m.kind){
        .hydrator=>{_=@atomicRmw(u8,&self.arena.active_hydrators,.Sub,1,.monotonic);},
        .verifier=>{_=@atomicRmw(u8,&self.arena.active_verifiers,.Sub,1,.monotonic);},
        .synthesizer=>{_=@atomicRmw(u8,&self.arena.active_synthesizers,.Sub,1,.monotonic);},
    }
}
pub fn tuiPoll(arena:*ArenaHeader,w:anytype)!void{
  try w.print("\r[H:{d} V:{d} S:{d}] ",.{@atomicLoad(u8,&arena.active_hydrators,.acquire),@atomicLoad(u8,&arena.active_verifiers,.acquire),@atomicLoad(u8,&arena.active_synthesizers,.acquire)});
  var j:usize=0;while(j<256):(j+=1){var m=&arena.msgs[j];if(@atomicLoad(u8,&m.status,.acquire)==2){
    switch(m.kind){
      .hydrator=>{try w.print("[Ctx7:{d}KB] ",.{m.result_len/1024});},
      .verifier=>{if(std.mem.indexOf(u8,m.result[0..m.result_len],"error:")==null){try w.print("[Build:PASS] ");}else{try w.print("[Build:FAIL] ");}},
      .synthesizer=>{try w.print("[Research:{d}n] ",.{@as(u16,@intCast(m.result_len/512))});},
    }
    @atomicStore(u8,&m.status,3,.release);
  }}
}
};