const std=@import("std");const L=std.os.linux;
const T=struct{name:[]const u8,desc:[]const u8,server:[]const u8,public:bool};
const tools=[_]T{
    .{.name="audit_governance",.desc="G01-G04 directive checks",.server="ralph",.public=false},
    .{.name="daily_reflection",.desc="Architectural alignment report",.server="ralph",.public=false},
    .{.name="verify_seal",.desc="Genesis Seal integrity",.server="ralph",.public=true},
    .{.name="ledger_stats",.desc="Entry counts + kind distribution",.server="ralph",.public=false},
    .{.name="propose_vote",.desc="GitHub governance vote",.server="ralph",.public=false},
    .{.name="check_vote",.desc="Tally reactions on issue",.server="ralph",.public=false},
    .{.name="query_last",.desc="Last N ledger entries",.server="ledger",.public=true},
    .{.name="query_by_kind",.desc="Filter by event kind",.server="ledger",.public=false},
    .{.name="verify_chain",.desc="Hash chain integrity",.server="ledger",.public=false},
    .{.name="stats",.desc="Ledger statistics",.server="ledger",.public=true},
    .{.name="peer_discovery",.desc="Online nodes + RTT",.server="synapse",.public=true},
    .{.name="convergence_stats",.desc="Intra-EU/transatlantic/APAC",.server="synapse",.public=true},
    .{.name="search",.desc="RAG search across 201 docs",.server="docs",.public=true},
    .{.name="list_topics",.desc="Documentation topic list",.server="docs",.public=true},
};
const GENESIS="7c242080";

fn jsonEscape(a:std.mem.Allocator,s:[]const u8)![]const u8{
    var b=std.ArrayListUnmanaged(u8){.items=&.{},.capacity=0};
    for(s)|c|{switch(c){'"'=>try b.appendSlice(a,"\\\""),'\\'=>try b.appendSlice(a,"\\\\"),'\n'=>try b.appendSlice(a,"\\n"),'\t'=>try b.appendSlice(a,"\\t"),else=>try b.append(a,c),};}
    return b.items;
}

fn toolsJson(a:std.mem.Allocator)![]const u8{
    var b=std.ArrayListUnmanaged(u8){.items=&.{},.capacity=0};
    try b.appendSlice(a,"[");
    for(tools,0)|t,i|{
        if(i>0)try b.append(a,',');
        const lock=if(t.public)"🔓" else "🔒";
        try b.appendSlice(a,"{\"name\":\"");
        try b.appendSlice(a,t.name);
        try b.appendSlice(a,"\",\"description\":\"");
        try b.appendSlice(a,lock);
        try b.appendSlice(a," [");
        try b.appendSlice(a,t.server);
        try b.appendSlice(a,"] ");
        try b.appendSlice(a,t.desc);
        try b.appendSlice(a,"\",\"inputSchema\":{\"type\":\"object\",\"properties\":{}}}");
    }
    try b.appendSlice(a,"]");
    return b.items;
}

fn respond(fd:i32,code:[]const u8,body:[]const u8)!void{
    var h:[256]u8=undefined;
    const hdr=try std.fmt.bufPrint(&h,"HTTP/1.1 {s}\r\nContent-Type: application/json\r\nContent-Length: {d}\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n",.{code,body.len});
    _=L.write(fd,hdr.ptr,hdr.len);_=L.write(fd,body.ptr,body.len);
}

fn json200(a:std.mem.Allocator,fd:i32,id:i64,body:[]const u8)!void{
    const r=try std.fmt.allocPrint(a,"{{\"jsonrpc\":\"2.0\",\"id\":{d},\"result\":{s}}}",.{id,body});
    try respond(fd,"200 OK",r);
}

fn jsonErr(fd:i32,id:i64,code:i32,msg:[]const u8)!void{
    var b:[512]u8=undefined;
    const r=try std.fmt.bufPrint(&b,"{{\"jsonrpc\":\"2.0\",\"id\":{d},\"error\":{{\"code\":{d},\"message\":\"{s}\"}}}}",.{id,code,msg});
    try respond(fd,"200 OK",r);
}

fn callTool(a:std.mem.Allocator,server:[]const u8,tool:[]const u8)![]const u8{
    _=a;_=server;_=tool;
    // Subprocess dispatch — spawn python3 tools/mcp-servers/{server}-mcp.py
    const cmd=try std.fmt.allocPrint(a,"python3 tools/mcp-servers/{s}-mcp.py",.{server});
    // For now: return placeholder. Real implementation forks+execves.
    return try std.fmt.allocPrint(a,"{{\"status\":\"ok\",\"tool\":\"{s}\",\"server\":\"{s}\"}}",.{tool,server});
}

pub fn main()!void{
    var arena=std.heap.ArenaAllocator.init(std.heap.page_allocator);defer arena.deinit();
    const a=arena.allocator();
    const tools_body=try toolsJson(a);

    const fd=L.socket(L.AF.INET,L.SOCK.STREAM|L.SOCK.CLOEXEC,0);const s:i32=@intCast(fd);defer _=L.close(s);
    const one:i32=1;_=L.setsockopt(s,L.SOL.SOCKET,L.SO.REUSEADDR,@ptrCast(&one),@sizeOf(i32));
    var addr=std.mem.zeroes(L.sockaddr.in);addr.family=L.AF.INET;addr.port=std.mem.nativeToBig(u16,9099);
    _=L.bind(s,@ptrCast(&addr),@sizeOf(L.sockaddr.in));_=L.listen(s,128);

    while(true){
        var ca:L.sockaddr.in=undefined;var al:u32=@sizeOf(L.sockaddr.in);
        const cu=L.accept4(s,@ptrCast(&ca),&al,L.SOCK.CLOEXEC);const c:i32=@intCast(cu);defer _=L.close(c);
        var buf:[4096]u8=undefined;const n=L.read(c,&buf,buf.len);if(n<=0)continue;
        const req=buf[0..@intCast(n)];

        // Parse HTTP
        var it=std.mem.splitScalar(u8,req,'\n');var parts=std.mem.splitScalar(u8,it.first(),' ');
        _=parts.first();const path=parts.next() orelse "/";

        if(std.mem.eql(u8,path,"/health")){
            const r=try std.fmt.allocPrint(a,"{{\"status\":\"ok\",\"servers\":4,\"tools\":{d},\"genesis\":\"{s}\"}}",.{tools.len,GENESIS});
            try respond(c,"200 OK",r);continue;
        }

        // Find body (after \r\n\r\n)
        const body_start=if(std.mem.indexOf(u8,req,"\r\n\r\n"))|idx| idx+4 else req.len;
        const body=req[body_start..];

        if(body.len<2){try respond(c,"400 Bad Request","{\"error\":\"empty body\"}");continue;}

        const parsed=std.json.parseFromSlice(std.json.Value,a,body,.{}) catch {
            try respond(c,"400 Bad Request","{\"error\":\"invalid JSON\"}");continue;
        };
        defer parsed.deinit();

        const root=parsed.value.object;
        const method=root.get("method") orelse {try respond(c,"400 Bad Request","{\"error\":\"missing method\"}");continue;};
        const rid=if(root.get("id"))|id| id.integer else @as(i64,0);

        if(std.mem.eql(u8,method.string,"tools/list")){
            try json200(a,c,rid,tools_body);continue;
        }
        if(std.mem.eql(u8,method.string,"initialize")){
            const r="{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{\"tools\":{\"listChanged\":false}},\"serverInfo\":{\"name\":\"vaked-mcp-gw\",\"version\":\"0.2.0\"}}";
            try json200(a,c,rid,r);continue;
        }
        if(std.mem.eql(u8,method.string,"tools/call")){
            const params=root.get("params") orelse {try jsonErr(c,rid,-32602,"missing params");continue;};
            const name=params.object.get("name") orelse {try jsonErr(c,rid,-32602,"missing name");continue;};

            // Auth check
            var public_tool=false;var tool_server:[]const u8="";
            for(tools)|t|{if(std.mem.eql(u8,t.name,name.string)){public_tool=t.public;tool_server=t.server;break;};}
            if(tool_server.len==0){try jsonErr(c,rid,-32601,"tool not found");continue;}
            if(!public_tool){
                const auth=if(std.mem.indexOf(u8,req,"Authorization: Bearer "))|idx| req[idx+22..std.mem.indexOfScalar(u8,req[idx..],'\r') orelse req.len+idx] else "";
                if(auth.len==0){try jsonErr(c,rid,-32000,"Auth required");continue;}
            }

            const result=try callTool(a,tool_server,name.string);
            try json200(a,c,rid,result);continue;
        }
        try jsonErr(c,rid,-32601,"unknown method");
    }
}
