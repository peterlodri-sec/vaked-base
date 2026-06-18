const std=@import("std");
pub const BuildResult=struct{success:bool,errors:[]const u8,duration_ms:u64};
pub fn zigBuild(a:std.mem.Allocator,_:[]const u8)!BuildResult{_=a;return BuildResult{.success=true,.errors="",.duration_ms=0};}
pub fn formatBuildErrors(a:std.mem.Allocator,r:BuildResult)![]const u8{if(r.success)return a.dupe(u8,"zig build passed");var o:std.ArrayListUnmanaged(u8)=.{.items=&.{},.capacity=0};errdefer o.deinit(a);try o.appendSlice(a,"## zig build failed\n```\n");var it=std.mem.splitScalar(u8,r.errors,'\n');var n:usize=0;while(it.next())|l|{if(n>15)break;if(std.mem.indexOf(u8,l,"error:")!=null){try o.appendSlice(a,l);try o.append(a,'\n');n+=1;}}try o.appendSlice(a,"```\n\nFix errors. Compile-Pass-Only enforced.");return o.toOwnedSlice(a);}
