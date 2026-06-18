const std=@import("std");
const MAX_D=5;
pub const ExecutionFrame=extern struct{id:u32 align(64),depth:u8,parent_id:u32,child_ids:[MAX_D]u32,child_count:u8,status:u8,frozen_prefix_offset:u32,frozen_prefix_len:u32,volatile_suffix:[2048]u8,result_payload:[4096]u8,result_len:u32,_pad:[44]u8};
pub const CallStack=extern struct{magic:u32 align(64),frame_count:u16,max_depth_reached:u8,frames:[32]ExecutionFrame};
pub const SpawnResult=struct{frame_id:u32,depth:u8};
pub fn spawnSubtask(stack:*CallStack,parent_id:u32,task:[]const u8,_:[]const u8)!SpawnResult{
    if(stack.frame_count>=32)return error.StackFull;
    const p=&stack.frames[parent_id];
    if(p.depth>=MAX_D)return error.MaxDepth;
    const cid=@atomicRmw(u16,&stack.frame_count,.Add,1,.monotonic);
    var c=&stack.frames[cid];c.id=cid;c.depth=p.depth+1;c.parent_id=parent_id;@atomicStore(u8,&c.status,1,.release);c.frozen_prefix_offset=p.frozen_prefix_offset;c.frozen_prefix_len=p.frozen_prefix_len;
    @memcpy(c.volatile_suffix[0..@min(task.len,2047)],task);
    p.child_ids[p.child_count]=cid;p.child_count+=1;
    if(c.depth>stack.max_depth_reached)stack.max_depth_reached=c.depth;
    return SpawnResult{.frame_id=cid,.depth=c.depth};
}
pub fn resolveChild(stack:*CallStack,child_id:u32,result:[]const u8)!void{
    var c=&stack.frames[child_id];@atomicStore(u8,&c.status,2,.release);c.result_len=@intCast(@min(result.len,4095));
    @memcpy(c.result_payload[0..c.result_len],result[0..c.result_len]);
    const p=&stack.frames[c.parent_id];
    _=try std.fmt.bufPrint(&p.volatile_suffix,"\n[D{d} done:{s}]",.{c.depth,result[0..@min(result.len,128)]});
}
pub fn forget(stack:*CallStack,frame_id:u32)void{var f=&stack.frames[frame_id];@atomicStore(u8,&f.status,3,.release);@memset(&f.volatile_suffix,0);}
pub fn renderBreadcrumb(stack:*CallStack,writer:anytype)!void{
    if(stack.frame_count==0)return;
    var path:[MAX_D+1]u32=undefined;var pl:usize=0;
    var deep:u32=0;var i:u16=0;while(i<stack.frame_count):(i+=1){if(@atomicLoad(u8,&stack.frames[i].status,.acquire)==1)deep=i;}
    var cur:u32=deep;
    while(true){path[pl]=cur;pl+=1;if(stack.frames[cur].parent_id==cur)break;if(cur==0)break;cur=stack.frames[cur].parent_id;}
    var j:usize=pl;while(j>0){j-=1;const f=stack.frames[path[j]];const icon:[*:0]const u8=switch(@atomicLoad(u8,&f.status,.acquire)){1=>"[*]",2=>"[OK]",3=>"[--]",else=>"[??]"};try writer.print("{s}[D{d}:{s}]",.{if(j<pl-1)"-->"else"",f.depth,icon});}
}
test "spawn"{
    var s:CallStack=undefined;@memset(@as([*]u8,@ptrCast(&s)),0);s.magic=0x7C242080;s.frames[0]=.{.id=0,.depth=0,.parent_id=0,.status=1};s.frame_count=1;
    const r=try spawnSubtask(&s,0,"Fix","");try std.testing.expectEqual(@as(u8,1),r.depth);try std.testing.expectEqual(@as(u32,1),r.frame_id);
}
test "breaker"{var s:CallStack=undefined;@memset(@as([*]u8,@ptrCast(&s)),0);s.frames[0].depth=5;s.frame_count=1;try std.testing.expectError(error.MaxDepth,spawnSubtask(&s,0,"",""));}