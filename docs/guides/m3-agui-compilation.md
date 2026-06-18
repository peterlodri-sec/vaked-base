# AG-UI Compilation — M3 Apple Silicon
**GENESIS_SEAL: c4a2e8f1 · Target: aarch64-darwin + iOS**

## Prerequisites
Zig 0.16.0 ✅ · Rust 1.96.0 ✅ · Swift 6.3.2 ✅ · Xcode CLI · iPhone (USB + Developer Mode)

## Local Daemon
```
cargo build --release --bin vaked-mobile
zig build-exe tools/vaked-parser/parser.zig -O ReleaseFast -mcpu=apple_m3 --name vaked-parser
```

## iOS App
```
cd AG-UI && xcodebuild -resolvePackageDependencies
xcodebuild -project AG-UI.xcodeproj -scheme AG-UI -configuration Release -sdk iphoneos build
xcrun devicectl device install app --device "UDID" build/Release-iphoneos/AG-UI.app
```

## Flow: C8 Pool → compressed diffs → M3 → USB → iPhone · <200ms
GENESIS_SEAL: d47e8b02
