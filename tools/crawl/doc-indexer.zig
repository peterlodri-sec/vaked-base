const std=@import("std");
const DocCdn=@import("doc_cdn.zig");
pub fn main()!void{
    var ar=std.heap.ArenaAllocator.init(std.heap.page_allocator); defer ar.deinit();
    const a=ar.allocator();
    var idx=DocCdn.DocIndex.init(a);
    // Index docs/ zone
    if(std.fs.openDirAbsolute("docs",.{.iterate=true}))|d|{
        defer d.close();
        var wk=try d.walk(a); defer wk.deinit();
        while(try wk.next())|e|{
            if(e.kind!=.file)continue;
            if(!std.mem.eql(u8,std.fs.path.extension(e.basename),".md"))continue;
            const c=d.readFileAlloc(a,e.path,10*1024*1024) catch continue; defer a.free(c);
            const fp=try std.fs.path.join(a,&.{"docs",e.path}); defer a.free(fp);
            try idx.ingest(fp,c,.zone,"vaked-base");
        }
    }else|_|{}
    // Index blog/ global
    if(std.fs.openDirAbsolute("blog",.{.iterate=true}))|d|{
        defer d.close();
        var wk=try d.walk(a); defer wk.deinit();
        while(try wk.next())|e|{
            if(e.kind!=.file)continue;
            if(!std.mem.eql(u8,std.fs.path.extension(e.basename),".md"))continue;
            const c=d.readFileAlloc(a,e.path,10*1024*1024) catch continue; defer a.free(c);
            const fp=try std.fs.path.join(a,&.{"blog",e.path}); defer a.free(fp);
            try idx.ingest(fp,c,.global,null);
        }
    }else|_|{}
    const se=std.io.getStdErr().writer();
    try se.print("doc-indexer: indexed\nGENESIS_SEAL: 7c242080\n",.{});
}
