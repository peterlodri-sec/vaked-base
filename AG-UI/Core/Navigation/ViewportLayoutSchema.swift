import SwiftUI

// AG-UI/Core/Navigation/ViewportLayoutSchema.swift
// GENESIS_SEAL 7c242080 — DOD re-skin. Zero OOP. Flat arrays. Hex only.

public enum UILayoutProfile: UInt8, CaseIterable {
    case denseMatrixGreen = 0
    case cleanGraphCyberpunk = 1
    case tacticalGraveyard = 2
}

// Value-type state. No class, no @Observable.
public struct ViewportLayoutState {
    public var activeProfile: UILayoutProfile

    public init(activeProfile: UILayoutProfile = .denseMatrixGreen) {
        self.activeProfile = activeProfile
    }
}

// Free function — mutates state in place. Replaces former cycleProfile() method.
public func cycleProfile(_ s: inout ViewportLayoutState) {
    let all = UILayoutProfile.allCases
    let next = (s.activeProfile.rawValue &+ 1) % UInt8(all.count)
    s.activeProfile = all[Int(next)]
}

// Flat palette arrays — indexed by UILayoutProfile.rawValue (0, 1, 2).
// Structs-of-arrays. No object graph.
public let bgHex: [String] = ["#040804", "#0a0a14", "#141414"]
public let surfaceHex: [String] = ["#0a140a", "#14141f", "#1e1e1e"]
public let fgHex: [String] = ["#c8f5c8", "#e0e8f5", "#d4d4d4"]
public let dimHex: [String] = ["#5a8c5a", "#6878a0", "#7a7a7a"]
public let accentHex: [String] = ["#00e660", "#00d4ff", "#b0b0b0"]
public let borderHex: [String] = ["#143a14", "#26304a", "#333333"]
public let okHex: [String] = ["#00e660", "#00ffa3", "#8fae8f"]
public let warnHex: [String] = ["#d4e600", "#ffb020", "#c2b070"]
public let errHex: [String] = ["#ff5544", "#ff3b6b", "#bd7a7a"]

public let profileNames: [String] = ["denseMatrixGreen", "cleanGraphCyberpunk", "tacticalGraveyard"]

// Compute-only Color(hex:) extension. No stored state, no asset catalog.
public extension Color {
    init(hex: String) {
        var s = hex
        if s.hasPrefix("#") {
            s.removeFirst()
        }
        var value: UInt64 = 0
        Scanner(string: s).scanHexInt64(&value)
        let r, g, b, a: Double
        switch s.count {
        case 3: // RGB (12-bit)
            r = Double((value >> 8) & 0xF) / 15.0
            g = Double((value >> 4) & 0xF) / 15.0
            b = Double(value & 0xF) / 15.0
            a = 1.0
        case 6: // RGB (24-bit)
            r = Double((value >> 16) & 0xFF) / 255.0
            g = Double((value >> 8) & 0xFF) / 255.0
            b = Double(value & 0xFF) / 255.0
            a = 1.0
        case 8: // ARGB (32-bit)
            a = Double((value >> 24) & 0xFF) / 255.0
            r = Double((value >> 16) & 0xFF) / 255.0
            g = Double((value >> 8) & 0xFF) / 255.0
            b = Double(value & 0xFF) / 255.0
        default:
            r = 0
            g = 0
            b = 0
            a = 1.0
        }
        self.init(.sRGB, red: r, green: g, blue: b, opacity: a)
    }
}
