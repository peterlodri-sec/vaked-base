export fn write(fd: c_int, buf: ?*const anyopaque, count: usize) isize {
    _ = fd;
    _ = buf;
    _ = count;
    return -1; // stub
}
